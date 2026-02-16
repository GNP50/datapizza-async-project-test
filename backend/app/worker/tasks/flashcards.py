"""
Celery task for on-demand flashcard generation.
"""
from celery import shared_task
import asyncio
import logging

from app.worker.pipeline.stage_flashcards import generate_flashcards_for_document
from uuid import UUID

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_flashcards_task(self, document_id: str):
    """Celery task wrapper for async flashcard generation"""
    logger.info(f"Starting flashcard generation task for document {document_id}")
    return asyncio.run(generate_flashcards_for_document(UUID(document_id)))
