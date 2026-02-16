"""
Stage B: Fact Atomization & Tree Structure

Extract atomic facts from document text using LLM.
Implements the BaseStage pattern for modular pipeline execution.
"""

import logging
from typing import Optional

from sqlalchemy import select

from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from app.services.database import db_manager
from app.models.document import Document, DocumentProcessingState
from app.models.message import ProcessingState
from app.models.fact import Fact, VerificationStatus
from app.services.storage import storage_manager
from app.services.fact_extraction import fact_extractor
from app.services.processing_cache_service import processing_cache_service
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


class FactAtomizationStage(BaseStage[dict, list[Fact]]):
    """
    Stage B: Fact Atomization & Tree Structure

    Extracts atomic facts from extracted document text using an LLM.
    Uses content-hash based caching to avoid re-processing identical text.

    Configuration:
        - cache_enabled: Enable/disable caching (default: True)
        - custom_params.max_facts: Maximum number of facts to extract (default: 50)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)

    async def execute(self, ctx: StageContext, input_data: dict) -> list[Fact]:
        """
        Extract atomic facts from document text.

        Args:
            ctx: Stage context with document_id
            input_data: Output from OCR stage (contains extracted text)

        Returns:
            List of Fact objects
        """
        document_id = ctx.document_id

        async with db_manager.session() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document or not document.extracted_content:
                raise ProcessingError("Document not extracted yet")

            # Get full text from storage or context
            full_text = ctx.get("extracted_text")
            if not full_text:
                # Fallback: download from storage
                md_path = document.file_path.replace(document.filename, f"{document.id}.md")
                try:
                    full_text_bytes = await storage_manager.download(md_path)
                    full_text = full_text_bytes.decode("utf-8")
                except Exception:
                    full_text = document.extracted_content

            # Check cache first (if enabled)
            facts = None
            if self.config.cache_enabled:
                content_hash = processing_cache_service.compute_content_hash(full_text)
                cache_stage = self.config.cache_stage_name or "fact_atomization"

                cached_result = await processing_cache_service.get_cached_result(
                    content_hash=content_hash,
                    stage=cache_stage,
                    db=db
                )

                if cached_result:
                    self.logger.info(
                        f"Fact atomization cache HIT for document {document_id} "
                        f"(hash={content_hash[:8]}...)"
                    )
                    facts = await self._create_facts_from_cache(db, document_id, cached_result)

            # Cache miss - extract facts using LLM
            if not facts:
                self.logger.info(f"Fact atomization cache MISS for document {document_id}")

                max_facts = self.config.custom_params.get("max_facts", 50)
                extraction_result = await fact_extractor.extract_facts(
                    text=full_text,
                    pages=None,  # TODO: Add page information from OCR result
                    max_facts=max_facts
                )

                # Save facts to database
                facts = []
                facts_for_cache = []

                for extracted_fact in extraction_result.facts:
                    fact = Fact(
                        document_id=document_id,
                        content=extracted_fact.content,
                        page_number=extracted_fact.page_number,
                        verification_status=VerificationStatus.PENDING,
                        confidence_score=extracted_fact.confidence
                    )
                    db.add(fact)
                    facts.append(fact)

                    # Prepare for caching
                    facts_for_cache.append({
                        "content": extracted_fact.content,
                        "page_number": extracted_fact.page_number,
                        "confidence": extracted_fact.confidence
                    })

                await db.commit()

                # Refresh facts to get IDs
                for fact in facts:
                    await db.refresh(fact)

                # Cache the result
                if self.config.cache_enabled:
                    content_hash = processing_cache_service.compute_content_hash(full_text)
                    cache_stage = self.config.cache_stage_name or "fact_atomization"

                    await processing_cache_service.set_cached_result(
                        content_hash=content_hash,
                        stage=cache_stage,
                        result_data={"facts": facts_for_cache},
                        document_id=document_id,
                        metadata={"fact_count": len(facts)},
                        db=db
                    )

            # Store facts in context for next stage
            ctx.set("facts", facts)
            ctx.set("fact_count", len(facts))

            self.logger.info(f"Fact atomization completed: {len(facts)} facts extracted")
            return facts

    async def _create_facts_from_cache(
        self,
        db,
        document_id,
        cached_result: dict
    ) -> list[Fact]:
        """Create Fact objects from cached data."""
        facts = []
        for cached_fact in cached_result["facts"]:
            fact = Fact(
                document_id=document_id,
                content=cached_fact["content"],
                page_number=cached_fact.get("page_number"),
                verification_status=VerificationStatus.PENDING,
                confidence_score=cached_fact.get("confidence", 0.8)
            )
            db.add(fact)
            facts.append(fact)

        await db.commit()

        # Refresh facts to get IDs
        for fact in facts:
            await db.refresh(fact)

        self.logger.info(f"Fact atomization completed from cache: {len(facts)} facts")
        return facts

    @classmethod
    def from_settings(cls, settings) -> 'FactAtomizationStage':
        """Create FactAtomizationStage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="fact_atomization",
            document_state=DocumentProcessingState.FACT_ATOMIZATION,
            message_state=ProcessingState.FACT_ATOMIZATION,
            cache_enabled=True,
            custom_params={
                "max_facts": 50
            }
        )
        return cls(config)
