"""
Stage D: Q&A Generation (Semantic Cache Preparation)

Generate question-answer pairs from verified facts.
Implements the BaseStage pattern for modular pipeline execution.
"""

import logging
from typing import Optional

from sqlalchemy import select

from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from app.services.database import db_manager
from app.models.document import DocumentProcessingState
from app.models.message import ProcessingState
from app.models.fact import Fact, VerificationStatus
from app.services.qa_generation import qa_generator
from app.services.processing_cache_service import processing_cache_service
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


class QAGenerationStage(BaseStage[int, list[dict]]):
    """
    Stage D: Q&A Generation (Semantic Cache Preparation)

    Generates question-answer pairs from verified/uncertain facts using an LLM.
    These Q&A pairs are later indexed into the vector store for semantic cache.

    Uses content-hash based caching to avoid re-generating Q&A for identical facts.

    Configuration:
        - cache_enabled: Enable/disable caching (default: True)
        - custom_params.max_pairs_per_fact: Max Q&A pairs per fact (default: 2)
        - custom_params.include_uncertain: Include uncertain facts (default: True)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)

    async def execute(self, ctx: StageContext, input_data: int) -> list[dict]:
        """
        Generate Q&A pairs from facts.

        Args:
            ctx: Stage context with document_id
            input_data: Verified count from previous stage (not used)

        Returns:
            List of Q&A pair dictionaries
        """
        document_id = ctx.document_id

        # Fetch verified/uncertain facts
        async with db_manager.session() as db:
            # Determine which statuses to include
            include_uncertain = self.config.custom_params.get("include_uncertain", True)
            statuses = [VerificationStatus.VERIFIED]
            if include_uncertain:
                statuses.append(VerificationStatus.UNCERTAIN)

            result = await db.execute(
                select(Fact)
                .where(Fact.document_id == document_id)
                .where(Fact.verification_status.in_(statuses))
            )
            facts = result.scalars().all()

            if not facts:
                self.logger.warning(f"No facts to generate Q&A pairs from for document {document_id}")
                return []

            # Convert facts to dict format
            facts_dict = [
                {
                    "id": fact.id,
                    "content": fact.content,
                    "verification_status": fact.verification_status.value,
                    "web_source_url": fact.web_source_url,
                    "confidence_score": fact.confidence_score
                }
                for fact in facts
            ]

            # Check cache first (if enabled)
            qa_pairs = None
            if self.config.cache_enabled:
                # Compute content hash (hash of all fact contents)
                facts_content = [f["content"] for f in facts_dict]
                content_hash = processing_cache_service.compute_content_hash(facts_content)
                cache_stage = self.config.cache_stage_name or "qa_generation"

                cached_result = await processing_cache_service.get_cached_result(
                    content_hash=content_hash,
                    stage=cache_stage,
                    db=db
                )

                if cached_result:
                    self.logger.info(
                        f"Q&A generation cache HIT for document {document_id} "
                        f"(hash={content_hash[:8]}...)"
                    )
                    qa_pairs = cached_result["qa_pairs"]

                    # Update fact_id references to current facts
                    qa_pairs = self._map_fact_ids(qa_pairs, facts_dict)

            # Cache miss - generate Q&A pairs
            if not qa_pairs:
                self.logger.info(f"Q&A generation cache MISS for document {document_id}")

                max_pairs_per_fact = self.config.custom_params.get("max_pairs_per_fact", 2)
                qa_result = await qa_generator.generate_qa_pairs(
                    facts=facts_dict,
                    max_pairs_per_fact=max_pairs_per_fact
                )

                # Convert to dict format and enrich metadata
                qa_pairs = []
                for qa in qa_result.qa_pairs:
                    # Find the fact content for caching purposes
                    fact_content = None
                    for f in facts_dict:
                        if f["id"] == qa.fact_id:
                            fact_content = f["content"]
                            break

                    qa_dict = {
                        "question": qa.question,
                        "answer": qa.answer,
                        "fact_id": qa.fact_id,
                        "confidence": qa.confidence,
                        "metadata": {
                            **(qa.metadata or {}),
                            "fact_content": fact_content  # Store for cache mapping
                        }
                    }
                    qa_pairs.append(qa_dict)

                # Cache the result
                if self.config.cache_enabled:
                    facts_content = [f["content"] for f in facts_dict]
                    content_hash = processing_cache_service.compute_content_hash(facts_content)
                    cache_stage = self.config.cache_stage_name or "qa_generation"

                    await processing_cache_service.set_cached_result(
                        content_hash=content_hash,
                        stage=cache_stage,
                        result_data={"qa_pairs": qa_pairs},
                        document_id=document_id,
                        metadata={"qa_count": len(qa_pairs), "fact_count": len(facts)},
                        db=db
                    )

            # Store Q&A pairs in context for next stage
            ctx.set("qa_pairs", qa_pairs)
            ctx.set("qa_count", len(qa_pairs))

            self.logger.info(f"Q&A generation completed: {len(qa_pairs)} pairs generated")
            return qa_pairs

    def _map_fact_ids(self, qa_pairs: list[dict], facts_dict: list[dict]) -> list[dict]:
        """Map cached fact IDs to current fact IDs using content matching."""
        content_to_id = {f["content"]: f["id"] for f in facts_dict}

        for qa in qa_pairs:
            # Try to map fact_id by content if available in metadata
            if qa.get("metadata") and "fact_content" in qa["metadata"]:
                fact_content = qa["metadata"]["fact_content"]
                if fact_content in content_to_id:
                    qa["fact_id"] = content_to_id[fact_content]

        return qa_pairs

    @classmethod
    def from_settings(cls, settings) -> 'QAGenerationStage':
        """Create QAGenerationStage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="qa_generation",
            document_state=DocumentProcessingState.QA_GENERATION,
            message_state=ProcessingState.QA_GENERATION,
            cache_enabled=True,
            custom_params={
                "max_pairs_per_fact": 2,
                "include_uncertain": True
            }
        )
        return cls(config)
