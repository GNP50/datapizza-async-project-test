"""
Production-ready document processing worker with modular pipeline architecture.

This worker implements a robust state-machine pipeline using the BaseStage pattern:
- Stage A: OCR & Extraction
- Stage B: Fact Atomization & Tree Structure
- Stage C: Web Verification (Fact Checking Agent)
- Stage D: Q&A Generation (Semantic Cache Preparation)
- Stage E: Vector Store Indexing

The pipeline is fully modular, configuration-driven, and supports:
- Resumption from any stage
- Parallel processing (configurable per stage)
- Caching (configurable per stage)
- Easy addition/removal of stages
"""

from celery import shared_task
from sqlalchemy import select
from uuid import UUID
import logging
import asyncio

from app.worker.celery_app import celery_app
from app.services.database import db_manager
from app.models.message import Message, MessageRole, ProcessingState
from app.models.document import Document
from app.core.config import get_settings

# Import pipeline infrastructure
from app.worker.pipeline.manager import PipelineManager
from app.worker.pipeline.stages import (
    OCRStage,
    FactAtomizationStage,
    WebVerificationStage,
    QAGenerationStage,
    VectorIndexingStage,
)

# Import utilities
from app.worker.utils.state import update_message_state, handle_processing_error
from app.worker.utils.response import generate_response
from app.worker.utils.errors import ProcessingError
from app.worker.utils.processing_cache import get_processing_cache


logger = logging.getLogger(__name__)


def create_document_pipeline(settings) -> PipelineManager:
    """
    Create the standard document processing pipeline.

    This factory function creates a pipeline with all standard stages,
    configured from application settings. Stages can be easily added,
    removed, or reordered.

    Args:
        settings: Application settings

    Returns:
        Configured PipelineManager instance
    """
    # Create stages from settings
    stages = [
        OCRStage.from_settings(settings),
        FactAtomizationStage.from_settings(settings),
        WebVerificationStage.from_settings(settings),
        QAGenerationStage.from_settings(settings),
        VectorIndexingStage.from_settings(settings),
    ]

    # Create pipeline manager
    pipeline = PipelineManager(
        stages=stages,
        name="document_processing"
    )

    logger.info(f"Created pipeline with stages: {pipeline.get_stage_order()}")
    return pipeline


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,  # ACK only after successful completion
    reject_on_worker_lost=True,  # Re-queue if worker dies
    autoretry_for=(Exception,),  # Auto-retry on exceptions
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=600,  # Max 10 minutes backoff
    retry_jitter=True  # Add randomness to avoid thundering herd
)
def process_message_task(
    self,
    message_id: str,
    only_document_id: str = None,
    skip_document_processing: bool = False,
    bypass_cache: bool = False
):
    """
    Celery task wrapper for async message processing.

    Args:
        message_id: The message ID to process
        only_document_id: If set, only process this single document (skip others).
                          Used when reprocessing a single document to avoid
                          re-running pipelines on all documents in the message.
        skip_document_processing: If True, skips all document processing and only generates response.
                                  Used when retrying a message but documents are already processed.
        bypass_cache: If True, bypasses semantic cache and uses deep RAG mode with full documents.
                      Used for "regenerate without cache" functionality.
    """
    # Use get_event_loop() to reuse existing loop or create new one safely
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(
            process_message(
                message_id,
                only_document_id=only_document_id,
                skip_document_processing=skip_document_processing,
                bypass_cache=bypass_cache
            )
        )
    except Exception as exc:
        logger.error(f"Task failed for message {message_id}: {exc}", exc_info=True)
        # Celery will handle retry based on autoretry_for
        raise


async def process_message(
    message_id: str,
    only_document_id: str = None,
    skip_document_processing: bool = False,
    bypass_cache: bool = False
) -> dict:
    """
    Main entry point for message processing.
    Implements a robust state-machine pipeline using the modular stage system.

    Args:
        message_id: The message ID to process
        only_document_id: If set, only process this single document (skip others).
                          Used when reprocessing a single document.
        skip_document_processing: If True, skips all document processing and only generates response.
                                  Used when retrying a message but documents are already processed.
        bypass_cache: If True, bypasses semantic cache and uses deep RAG mode with full documents.
                      Used for "regenerate without cache" functionality.
    """
    logger.info(
        f"Starting processing for message {message_id}" +
        (f" (single document: {only_document_id})" if only_document_id else "") +
        (f" (skip document processing: {skip_document_processing})" if skip_document_processing else "") +
        (f" (bypass cache: {bypass_cache})" if bypass_cache else "")
    )

    # Get processing cache
    processing_cache = get_processing_cache()

    # Check in-memory cache first (only for full message processing, not single document reprocessing)
    if not only_document_id:
        if not processing_cache.add(message_id):
            logger.warning(
                f"Message {message_id} is already being processed by this worker instance. "
                f"Skipping duplicate task."
            )
            return {"skipped": True, "reason": "already_processing_in_worker", "message_id": message_id}

    try:
        # Fetch message and documents
        async with db_manager.session() as db:
            result = await db.execute(select(Message).where(Message.id == UUID(message_id)))
            message = result.scalar_one_or_none()

            if not message:
                logger.error(f"Message {message_id} not found")
                return {"error": "Message not found", "message_id": message_id}

            chat_id = message.chat_id
            content = message.content

            # Find all FAILED user messages in this chat that came before this message
            # These need to be reprocessed (documents only, no response generation)
            failed_messages_result = await db.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .where(Message.role == MessageRole.USER)
                .where(Message.processing_state == ProcessingState.FAILED)
                .where(Message.created_at < message.created_at)
                .order_by(Message.created_at.asc())
            )
            failed_messages = failed_messages_result.scalars().all()

            if only_document_id:
                # Only fetch the single document to reprocess
                result = await db.execute(
                    select(Document).where(Document.id == UUID(only_document_id))
                )
            else:
                result = await db.execute(
                    select(Document).where(Document.message_id == message.id)
                )
            documents = result.scalars().all()

        # Skip all document processing if flag is set
        if skip_document_processing:
            logger.info(
                f"⏭️  SKIPPING document processing for message {message_id} "
                f"(skip_document_processing=True)"
            )

        if not skip_document_processing:
            # Create pipeline from settings
            settings = get_settings()
            pipeline = create_document_pipeline(settings)

            # First, process documents from any FAILED messages (without generating responses)
            if failed_messages and not only_document_id:
                logger.info(f"Found {len(failed_messages)} failed messages to reprocess for chat {chat_id}")

                for failed_msg in failed_messages:
                    # Get all documents for this failed message
                    async with db_manager.session() as db:
                        failed_docs_result = await db.execute(
                            select(Document).where(Document.message_id == failed_msg.id)
                        )
                        failed_docs = failed_docs_result.scalars().all()

                    # Process these documents through the pipeline
                    if failed_docs:
                        logger.info(
                            f"Processing {len(failed_docs)} documents from failed message {failed_msg.id}"
                        )
                        failed_doc_ids = [doc.id for doc in failed_docs]

                        # Use pipeline batch execution
                        await pipeline.execute_batch(
                            document_ids=failed_doc_ids,
                            message_id=failed_msg.id,
                            chat_id=chat_id,
                            parallel=settings.documents_parallel,
                            max_concurrency=settings.documents_max_concurrency,
                            max_retries=settings.documents_max_retries
                        )

                        # Mark the failed message as completed (but don't generate response)
                        async with db_manager.session() as db:
                            result = await db.execute(select(Message).where(Message.id == failed_msg.id))
                            msg = result.scalar_one_or_none()
                            if msg:
                                msg.processing_state = ProcessingState.COMPLETED
                                await db.commit()

                        logger.info(f"Completed processing failed message {failed_msg.id}")

            # Then process documents from the current message
            if documents:
                logger.info(f"Processing {len(documents)} documents for message {message_id}")

                document_ids = [doc.id for doc in documents]

                # Use pipeline batch execution
                await pipeline.execute_batch(
                    document_ids=document_ids,
                    message_id=UUID(message_id),
                    chat_id=chat_id,
                    parallel=settings.documents_parallel and not only_document_id,
                    max_concurrency=settings.documents_max_concurrency,
                    max_retries=settings.documents_max_retries
                )
        else:
            logger.info(
                f"Skipping document processing for message {message_id} "
                f"(skip_document_processing=True)"
            )

        # Collect ALL processed documents in this chat (not just current message)
        # so the user can ask follow-up questions about previously uploaded docs
        async with db_manager.session() as db:
            all_docs_result = await db.execute(
                select(Document)
                .join(Message, Document.message_id == Message.id)
                .where(Message.chat_id == chat_id)
                .where(Document.processed == True)
            )
            all_chat_documents = all_docs_result.scalars().all()

        # Generate response using all available documents in the chat
        await update_message_state(message_id, ProcessingState.GENERATING_RESPONSE)
        response_content, response_metadata = await generate_response(
            UUID(message_id),
            all_chat_documents,
            bypass_cache=bypass_cache
        )

        # Save assistant message with metadata
        async with db_manager.session() as db:
            assistant_message = Message(
                chat_id=chat_id,
                role=MessageRole.ASSISTANT,
                content=response_content,
                processing_state=ProcessingState.COMPLETED,
                response_cached=response_metadata.get("cached", False),
                response_type=response_metadata.get("response_type", "conversational"),
                response_metadata=response_metadata
            )
            db.add(assistant_message)
            await db.commit()

            # Mark original message as completed
            result = await db.execute(select(Message).where(Message.id == UUID(message_id)))
            message = result.scalar_one_or_none()
            if message:
                message.processing_state = ProcessingState.COMPLETED
                await db.commit()

        logger.info(f"Processing completed for message {message_id}")
        return {"status": "completed", "message_id": message_id}

    except Exception as e:
        logger.error(f"Processing failed for message {message_id}: {e}", exc_info=True)
        await handle_processing_error(message_id, e)
        return {"error": str(e), "message_id": message_id}

    finally:
        # Always remove from processing cache when done (success or failure)
        # Only remove if we were processing the full message (not single document reprocessing)
        if not only_document_id:
            processing_cache.remove(message_id)
            logger.debug(f"Removed message {message_id} from processing cache")
