"""
State management utilities for worker tasks.

Handles updating processing states for messages and documents.
"""
import logging
from uuid import UUID
from sqlalchemy import select

from app.services.database import db_manager
from app.models.message import Message, ProcessingState
from app.models.document import Document, DocumentProcessingState

logger = logging.getLogger(__name__)


async def update_message_state(message_id: str, state: ProcessingState):
    """Update message processing state"""
    try:
        async with db_manager.session() as db:
            result = await db.execute(select(Message).where(Message.id == UUID(message_id)))
            message = result.scalar_one_or_none()
            if message:
                message.processing_state = state
                await db.commit()
                logger.info(f"Message {message_id} state updated to {state.value}")
    except Exception as e:
        logger.error(f"Failed to update message state: {e}")


async def update_document_state(document_id: UUID, state: DocumentProcessingState):
    """Update document processing state"""
    try:
        async with db_manager.session() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document:
                document.processing_state = state
                await db.commit()
                logger.info(f"Document {document_id} state updated to {state.value}")
    except Exception as e:
        logger.error(f"Failed to update document state: {e}")


async def handle_processing_error(message_id: str, error: Exception):
    """Handle processing errors gracefully"""
    logger.error(f"Handling error for message {message_id}: {error}")
    try:
        async with db_manager.session() as db:
            result = await db.execute(select(Message).where(Message.id == UUID(message_id)))
            message = result.scalar_one_or_none()
            if message:
                message.processing_state = ProcessingState.FAILED
                await db.commit()
    except Exception as e:
        logger.error(f"Failed to update error state: {e}")
