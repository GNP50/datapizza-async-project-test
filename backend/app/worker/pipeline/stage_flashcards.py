"""
Flashcard Generation Stage (On-Demand)

Generates study flashcards from verified facts.
This is a standalone stage that can be triggered on-demand via API.
"""

import logging
from uuid import UUID
from sqlalchemy import select

from app.services.database import db_manager
from app.models.document import Document
from app.models.fact import Fact, VerificationStatus
from app.models.flashcard import Flashcard
from app.services.flashcard_generation import flashcard_generator
from app.services.storage import storage_manager


logger = logging.getLogger(__name__)


async def generate_flashcards_for_document(document_id: UUID) -> dict:
    """
    Generate flashcards for a document from its verified facts.

    This function maintains the original interface for backward compatibility
    with the flashcards.py task, but uses the underlying flashcard service.

    Args:
        document_id: ID of the document to generate flashcards for

    Returns:
        Dictionary with generation results
    """
    logger.info(f"Generating flashcards for document {document_id}")

    try:
        async with db_manager.session() as db:
            # Get document
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document:
                logger.error(f"Document {document_id} not found")
                return {"error": "Document not found", "document_id": str(document_id)}

            # Get verified/uncertain facts
            result = await db.execute(
                select(Fact)
                .where(Fact.document_id == document_id)
                .where(Fact.verification_status.in_([
                    VerificationStatus.VERIFIED,
                    VerificationStatus.UNCERTAIN
                ]))
            )
            facts = result.scalars().all()

            if not facts:
                logger.warning(f"No facts found for flashcard generation for document {document_id}")
                return {
                    "status": "completed",
                    "document_id": str(document_id),
                    "flashcards_count": 0,
                    "message": "No facts available for flashcard generation"
                }

            # Convert facts to dict format for service
            facts_dict = [
                {
                    "id": fact.id,
                    "content": fact.content,
                    "verification_status": fact.verification_status.value.lower(),
                    "web_source_url": fact.web_source_url,
                    "confidence_score": fact.confidence_score
                }
                for fact in facts
            ]

            # Get document context (optional)
            document_context = None
            try:
                md_path = document.file_path.replace(document.filename, f"{document.id}.md")
                full_text_bytes = await storage_manager.download(md_path)
                full_text = full_text_bytes.decode("utf-8")
                # Use first 500 chars as context
                document_context = full_text[:500] if full_text else None
            except Exception as e:
                logger.warning(f"Could not load document context: {e}")

            # Generate flashcards using service
            generation_result = await flashcard_generator.generate_flashcards(
                facts=facts_dict,
                max_cards_per_fact=2,
                document_context=document_context
            )

            # Save flashcards to database
            flashcard_count = 0
            for flashcard_item in generation_result.flashcards:
                flashcard = Flashcard(
                    document_id=document_id,
                    fact_id=UUID(flashcard_item.fact_id) if flashcard_item.fact_id else None,
                    front=flashcard_item.front,
                    back=flashcard_item.back,
                    category=flashcard_item.category,
                    difficulty=flashcard_item.difficulty,
                    confidence=flashcard_item.confidence
                )
                db.add(flashcard)
                flashcard_count += 1

            await db.commit()

            logger.info(
                f"Flashcard generation completed for document {document_id}: "
                f"{flashcard_count} flashcards generated"
            )

            return {
                "status": "completed",
                "document_id": str(document_id),
                "flashcards_count": flashcard_count,
                "generation_method": generation_result.generation_method
            }

    except Exception as e:
        logger.error(f"Flashcard generation failed for document {document_id}: {e}", exc_info=True)
        return {
            "error": str(e),
            "document_id": str(document_id)
        }
