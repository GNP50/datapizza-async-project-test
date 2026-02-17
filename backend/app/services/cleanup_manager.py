"""
Centralized cleanup manager for documents and messages.
Handles deletion of all related data: facts, flashcards, cache, vectors, and DB records.
"""
import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.message import Message, MessageRole
from app.models.fact import Fact
from app.models.flashcard import Flashcard
from app.services.processing_cache_service import processing_cache_service
from app.services.rag.vectorstore import vectorstore

logger = logging.getLogger(__name__)


class CleanupManager:
    """Centralized manager for cleaning up all data related to documents and messages."""

    async def cleanup_document(
        self,
        document_id: UUID,
        db: AsyncSession,
        stages_to_clean: list[str] | None = None,
        delete_document: bool = False
    ) -> dict:
        """
        Clean up all data associated with a document.

        Args:
            document_id: The document ID to clean up
            db: Database session
            stages_to_clean: Optional list of cache stages to invalidate.
                           If None, cleans all stages.
            delete_document: If True, also delete the document itself from DB

        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "document_id": str(document_id),
            "facts_deleted": 0,
            "flashcards_deleted": 0,
            "cache_entries_deleted": 0,
            "vectors_deleted": 0,
            "document_deleted": False,
        }

        logger.info(f"Starting cleanup for document {document_id}")

        # 0. Clear document summary if cleaning vector_indexing stage
        # Summary is generated during vector indexing, so clear it when re-indexing
        # BUT preserve extracted_content (from OCR stage) as it's expensive to regenerate
        try:
            if stages_to_clean is None or "vector_indexing" in stages_to_clean:
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc and doc.summary:
                    doc.summary = None
                    await db.commit()
                    logger.info(f"Cleared summary for document {document_id} (extracted_content preserved)")
        except Exception as e:
            logger.warning(f"Failed to clear summary for document {document_id}: {e}")

        # 1. Delete facts
        try:
            result = await db.execute(
                select(Fact).where(Fact.document_id == document_id)
            )
            facts = result.scalars().all()
            for fact in facts:
                await db.delete(fact)
            stats["facts_deleted"] = len(facts)
            logger.info(f"Deleted {len(facts)} facts for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to delete facts for document {document_id}: {e}")

        # 2. Delete flashcards
        try:
            result = await db.execute(
                select(Flashcard).where(Flashcard.document_id == document_id)
            )
            flashcards = result.scalars().all()
            for flashcard in flashcards:
                await db.delete(flashcard)
            stats["flashcards_deleted"] = len(flashcards)
            logger.info(f"Deleted {len(flashcards)} flashcards for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to delete flashcards for document {document_id}: {e}")

        # 3. Invalidate processing cache (SKIP OCR - it's expensive and doesn't change)
        try:
            # All stages EXCEPT OCR (OCR cache is preserved since it's expensive to recompute)
            all_stages_except_ocr = ["fact_extraction", "web_verification", "qa_generation", "vector_indexing"]
            stages = stages_to_clean if stages_to_clean else all_stages_except_ocr

            # Filter out OCR stage if it was explicitly requested (we never clean OCR)
            stages = [s for s in stages if s != "ocr"]

            for stage in stages:
                deleted = await processing_cache_service.invalidate_cache(
                    stage=stage,
                    document_id=document_id,
                    db=db
                )
                stats["cache_entries_deleted"] += deleted

            logger.info(f"Invalidated {stats['cache_entries_deleted']} cache entries for document {document_id} (OCR preserved)")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache for document {document_id}: {e}")

        # 4. Delete vectors from vectorstore
        try:
            await vectorstore.a_delete_by_document(document_id)
            stats["vectors_deleted"] = 1  # Qdrant doesn't return count
            logger.info(f"Deleted vectors for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to delete vectors for document {document_id}: {e}")

        # 5. Delete the document itself if requested
        if delete_document:
            try:
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    await db.delete(doc)
                    stats["document_deleted"] = True
                    logger.info(f"Deleted document {document_id}")
            except Exception as e:
                logger.warning(f"Failed to delete document {document_id}: {e}")

        # Commit all database changes
        await db.commit()

        logger.info(f"Cleanup completed for document {document_id}: {stats}")
        return stats

    async def cleanup_message(
        self,
        message_id: UUID,
        db: AsyncSession,
        delete_message: bool = False,
        delete_subsequent_messages: bool = True,
        skip_current_message_documents: bool = False
    ) -> dict:
        """
        Clean up all data associated with a message and optionally subsequent messages.

        Args:
            message_id: The message ID to clean up
            db: Database session
            delete_message: If True, also delete the message itself from DB
            delete_subsequent_messages: If True, delete all messages that come after this one
            skip_current_message_documents: If True, don't clean documents of the current message
                                           (useful when documents were already cleaned separately)

        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "message_id": str(message_id),
            "documents_cleaned": 0,
            "messages_deleted": 0,
            "total_facts_deleted": 0,
            "total_flashcards_deleted": 0,
            "total_cache_entries_deleted": 0,
            "total_vectors_deleted": 0,
        }

        logger.info(f"Starting cleanup for message {message_id}")

        # Get the message
        result = await db.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            logger.warning(f"Message {message_id} not found")
            return stats

        # 1. Clean up all documents associated with this message (if not skipped)
        if not skip_current_message_documents:
            result = await db.execute(
                select(Document).where(Document.message_id == message_id)
            )
            documents = result.scalars().all()

            for doc in documents:
                doc_stats = await self.cleanup_document(
                    document_id=doc.id,
                    db=db,
                    delete_document=delete_message  # Delete documents if we're deleting the message
                )
                stats["documents_cleaned"] += 1
                stats["total_facts_deleted"] += doc_stats["facts_deleted"]
                stats["total_flashcards_deleted"] += doc_stats["flashcards_deleted"]
                stats["total_cache_entries_deleted"] += doc_stats["cache_entries_deleted"]
                stats["total_vectors_deleted"] += doc_stats["vectors_deleted"]

        # 2. Delete subsequent messages if requested
        if delete_subsequent_messages:
            result = await db.execute(
                select(Message)
                .where(Message.chat_id == message.chat_id)
                .where(Message.created_at > message.created_at)
                .order_by(Message.created_at.asc())
            )
            subsequent_messages = result.scalars().all()

            for subsequent_message in subsequent_messages:
                # Recursively clean up subsequent messages and their documents
                subsequent_stats = await self.cleanup_message(
                    message_id=subsequent_message.id,
                    db=db,
                    delete_message=True,  # Always delete subsequent messages
                    delete_subsequent_messages=False  # We're already processing them in order
                )
                stats["messages_deleted"] += 1
                stats["documents_cleaned"] += subsequent_stats["documents_cleaned"]
                stats["total_facts_deleted"] += subsequent_stats["total_facts_deleted"]
                stats["total_flashcards_deleted"] += subsequent_stats["total_flashcards_deleted"]
                stats["total_cache_entries_deleted"] += subsequent_stats["total_cache_entries_deleted"]
                stats["total_vectors_deleted"] += subsequent_stats["total_vectors_deleted"]

        # 3. Delete the message itself if requested
        if delete_message:
            try:
                await db.delete(message)
                logger.info(f"Deleted message {message_id}")
            except Exception as e:
                logger.warning(f"Failed to delete message {message_id}: {e}")

        # Commit all changes
        await db.commit()

        logger.info(f"Cleanup completed for message {message_id}: {stats}")
        return stats


# Global singleton instance
cleanup_manager = CleanupManager()
