"""
Stage C: Web Verification (Fact Checking Agent)

Verify each fact using web search + LLM analysis.
Implements the BaseStage pattern for modular pipeline execution.
"""

import json
import logging
import asyncio
from asyncio import Semaphore
from typing import Optional

from sqlalchemy import select

from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from app.services.database import db_manager
from app.models.document import Document, DocumentProcessingState
from app.models.message import ProcessingState
from app.models.fact import Fact, VerificationStatus
from app.services.search import search_service
from app.services.search.web_content_extractor import web_content_extractor
from app.services.llm import llm_client
from app.services.processing_cache_service import processing_cache_service
from app.services.rag.vectorstore import vectorstore
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


VERIFICATION_SYSTEM_PROMPT = """You are a fact-verification judge. You receive a CLAIM extracted from a document and a set of WEB SEARCH SNIPPETS.

Your job:
1. FIRST, check if the snippets contain inappropriate/adult content (pornography, explicit sexual content, etc.). If so, mark them as inappropriate.
2. THEN, decide whether the snippets SUPPORT, CONTRADICT, or are IRRELEVANT to the claim.
3. Assign a verdict and confidence score.

VERDICT definitions:
- "VERIFIED": at least one snippet clearly supports the claim with matching data/details.
- "DEBUNKED": at least one snippet clearly contradicts the claim with opposing data/details.
- "UNCERTAIN": snippets are tangentially related or insufficient to judge.
- "INAPPROPRIATE": snippets contain adult/inappropriate content unrelated to legitimate fact-checking.

CONFIDENCE scoring (0.0 – 1.0):
- 0.9–1.0: snippet directly confirms/denies with hard data
- 0.7–0.8: snippet strongly suggests confirmation/denial
- 0.5–0.6: some indirect evidence
- below 0.5: very weak or no evidence

Respond with ONLY a JSON object (no extra text):
{
  "verdict": "VERIFIED|DEBUNKED|UNCERTAIN|INAPPROPRIATE",
  "confidence": 0.85,
  "reasoning": "Brief explanation (1-2 sentences) of why this verdict was chosen",
  "best_source_index": 0,
  "inappropriate_content": false
}

Where best_source_index is the 0-based index of the most relevant snippet (or null if none are relevant).
Set inappropriate_content to true if any snippets contain adult/sexual content."""


class WebVerificationStage(BaseStage[list[Fact], int]):
    """
    Stage C: Web Verification (Fact Checking Agent)

    Verifies each fact using:
    1. Web search (DuckDuckGo)
    2. LLM judge to analyze search results
    3. Optional content extraction and indexing

    Supports parallel processing of facts with configurable concurrency.
    Uses content-hash based caching to avoid re-verifying identical facts.

    Configuration:
        - parallel_enabled: Process facts in parallel (default: False)
        - max_concurrency: Maximum concurrent verifications (default: 3)
        - cache_enabled: Enable/disable caching (default: True)
        - custom_params.web_search_enabled: Enable/disable web search (default: True)
        - custom_params.max_search_results: Max search results per fact (default: 5)
        - custom_params.index_verified_sources: Index verified source content (default: True)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)

    async def execute(self, ctx: StageContext, input_data: list[Fact]) -> int:
        """
        Verify facts using web search and LLM judge.

        Args:
            ctx: Stage context with document_id
            input_data: List of Fact objects from previous stage

        Returns:
            Number of verified facts
        """
        document_id = ctx.document_id
        facts = input_data or ctx.get("facts", [])

        if not facts:
            self.logger.warning(f"No facts to verify for document {document_id}")
            return 0

        # Check if web search is enabled for this document
        web_search_enabled = await self._get_web_search_setting(document_id)
        if not web_search_enabled:
            self.logger.info(f"Web search disabled for document {document_id}, marking facts as pending")
            await self._mark_facts_pending(facts)
            return 0

        # Verify facts (parallel or sequential based on config)
        verified_count = 0
        if self.config.parallel_enabled and len(facts) > 1:
            verified_count = await self._verify_parallel(ctx, facts)
        else:
            verified_count = await self._verify_sequential(ctx, facts)

        # Store result in context
        ctx.set("verified_count", verified_count)
        ctx.set("total_facts", len(facts))

        self.logger.info(f"Web verification completed: {verified_count}/{len(facts)} facts verified")
        return verified_count

    async def _verify_sequential(self, ctx: StageContext, facts: list[Fact]) -> int:
        """Verify facts sequentially."""
        self.logger.info(f"Processing {len(facts)} facts sequentially")
        verified_count = 0

        for fact in facts:
            result = await self._verify_single_fact(ctx, fact)
            if result == 1:
                verified_count += 1

        return verified_count

    async def _verify_parallel(self, ctx: StageContext, facts: list[Fact]) -> int:
        """Verify facts in parallel with concurrency limit."""
        semaphore = Semaphore(self.config.max_concurrency)

        async def verify_with_retry(fact: Fact) -> int:
            """Verify a single fact with retry logic."""
            async with semaphore:
                for attempt in range(self.config.max_retries):
                    try:
                        return await self._verify_single_fact(ctx, fact)
                    except Exception as e:
                        if attempt < self.config.max_retries - 1:
                            self.logger.warning(
                                f"Web verification retry {attempt + 1}/{self.config.max_retries} "
                                f"for fact {fact.id}: {e}"
                            )
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            self.logger.error(
                                f"Web verification failed after {self.config.max_retries} retries "
                                f"for fact {fact.id}"
                            )
                            return 0

        # Process all facts in parallel
        self.logger.info(
            f"Processing {len(facts)} facts in parallel "
            f"with max_concurrency={self.config.max_concurrency}"
        )
        tasks = [verify_with_retry(fact) for fact in facts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count verified facts
        verified_count = 0
        for result in results:
            if isinstance(result, int):
                verified_count += result

        return verified_count

    async def _verify_single_fact(self, ctx: StageContext, fact: Fact) -> int:
        """
        Verify a single fact with web search + LLM judge.
        Returns 1 if verified, 0 otherwise.
        """
        document_id = ctx.document_id

        # Compute content hash ONCE at the start to ensure consistency
        content_hash = processing_cache_service.compute_content_hash(fact.content)
        cache_stage = self.config.cache_stage_name or "web_verification"

        try:
            # Check cache first (if enabled)
            if self.config.cache_enabled:
                cache_key = processing_cache_service.compute_cache_key(content_hash, cache_stage)

                self.logger.info(
                    f"🔍 Cache lookup for fact {fact.id}:\n"
                    f"  Content (first 100 chars): {fact.content[:100]!r}\n"
                    f"  Content hash: {content_hash}\n"
                    f"  Cache key: {cache_key}"
                )

                cached_result = await processing_cache_service.get_cached_result(
                    content_hash=content_hash,
                    stage=cache_stage
                    # Note: Not filtering by document_id to allow cache hits across documents
                    # with identical fact content. document_id is still stored for tracking.
                )

                if cached_result:
                    self.logger.info(f"✅ Web verification cache HIT for fact {fact.id}")
                    await self._update_fact_from_cache(fact, cached_result)
                    return 1 if cached_result["verification_status"] == "VERIFIED" else 0

            # Cache miss — web search + LLM judge
            self.logger.info(f"❌ Web verification cache MISS for fact {fact.id}")

            max_results = self.config.custom_params.get("max_search_results", 5)
            search_response = await search_service.search(
                query=fact.content,
                max_results=max_results
            )

            if search_response.results:
                # Use LLM to analyze search results
                judge_result = await self._llm_judge_fact(fact.content, search_response.results)

                verdict_str = judge_result["verdict"]
                all_source_urls = [r.url for r in search_response.results if r.url]

                verification_data = {
                    "verification_status": verdict_str,
                    "web_source_url": judge_result["best_source_url"],
                    "all_source_urls": all_source_urls,
                    "confidence_score": judge_result["confidence"],
                    "verification_reasoning": judge_result["reasoning"]
                }

                status_enum = VerificationStatus[verdict_str]

                # Extract and index web content from best source (if verified)
                if verdict_str == "VERIFIED" and judge_result["best_source_url"]:
                    index_sources = self.config.custom_params.get("index_verified_sources", True)
                    if index_sources and ctx.chat_id:
                        await self._index_verified_source(
                            ctx,
                            fact,
                            judge_result["best_source_url"]
                        )
            else:
                # No search results at all
                verification_data = {
                    "verification_status": "UNCERTAIN",
                    "web_source_url": None,
                    "all_source_urls": [],
                    "confidence_score": 0.3,
                    "verification_reasoning": "No web search results found for this claim."
                }
                status_enum = VerificationStatus.UNCERTAIN

            # Update fact in database
            await self._update_fact(fact, verification_data, status_enum)

            # Cache the result (reuse content_hash computed at the start)
            if self.config.cache_enabled:
                cache_key = processing_cache_service.compute_cache_key(content_hash, cache_stage)
                self.logger.info(
                    f"💾 Storing cache for fact {fact.id}:\n"
                    f"  Content hash: {content_hash}\n"
                    f"  Cache key: {cache_key}"
                )

                await processing_cache_service.set_cached_result(
                    content_hash=content_hash,
                    stage=cache_stage,
                    result_data=verification_data,
                    document_id=document_id,
                    metadata={"fact_content": fact.content}
                )

            return 1 if status_enum == VerificationStatus.VERIFIED else 0

        except Exception as e:
            self.logger.warning(f"Failed to verify fact {fact.id}: {e}")
            return 0

    async def _llm_judge_fact(self, fact_content: str, search_results: list) -> dict:
        """Use LLM to judge whether search results support/contradict a fact."""
        snippets_text = "\n\n".join([
            f"[Source {i}] {r.title}\nURL: {r.url}\nSnippet: {r.snippet}"
            for i, r in enumerate(search_results)
        ])

        prompt = f"""CLAIM: {fact_content}

WEB SEARCH RESULTS:
{snippets_text}

Analyze the search results and provide your verdict."""

        try:
            response = await llm_client.a_invoke(
                input=prompt,
                system_prompt=VERIFICATION_SYSTEM_PROMPT
            )

            response_text = response.text.strip()
            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)

            # Check for inappropriate content
            if result.get("inappropriate_content", False) or result.get("verdict", "").upper() == "INAPPROPRIATE":
                self.logger.warning(f"LLM detected inappropriate content for: {fact_content[:50]}...")
                return {
                    "verdict": "UNCERTAIN",
                    "confidence": 0.0,
                    "reasoning": "Search results contained inappropriate content and were filtered out.",
                    "best_source_url": None
                }

            verdict = result.get("verdict", "UNCERTAIN").upper()
            if verdict not in ("VERIFIED", "DEBUNKED", "UNCERTAIN"):
                verdict = "UNCERTAIN"

            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            best_idx = result.get("best_source_index")
            best_url = None
            if best_idx is not None and 0 <= best_idx < len(search_results):
                best_url = search_results[best_idx].url

            return {
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": result.get("reasoning", ""),
                "best_source_url": best_url
            }

        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"LLM judge failed, falling back to heuristic: {e}")
            # Fallback: simple heuristic if LLM fails
            if search_results:
                return {
                    "verdict": "UNCERTAIN",
                    "confidence": 0.5,
                    "reasoning": "LLM analysis unavailable; search results found but not analyzed.",
                    "best_source_url": search_results[0].url
                }
            return {
                "verdict": "UNCERTAIN",
                "confidence": 0.3,
                "reasoning": "No search results found and LLM analysis unavailable.",
                "best_source_url": None
            }

    async def _index_verified_source(
        self,
        ctx: StageContext,
        fact: Fact,
        source_url: str
    ) -> None:
        """Extract and index content from verified source."""
        try:
            chunks = await web_content_extractor.process_url_to_chunks(
                url=source_url,
                query_context=fact.content,
                llm_client=llm_client.client,
                chat_id=ctx.chat_id,
                source_type="fact_verification"
            )

            if chunks:
                await vectorstore.a_add(chunks, chat_id=ctx.chat_id)
                self.logger.info(
                    f"Indexed {len(chunks)} chunks from verified source for fact {fact.id}"
                )

        except Exception as e:
            # Don't fail the whole verification if content extraction fails
            self.logger.warning(f"Failed to extract/index content from {source_url}: {e}")

    async def _update_fact(
        self,
        fact: Fact,
        verification_data: dict,
        status_enum: VerificationStatus
    ) -> None:
        """Update fact with verification results."""
        async with db_manager.session() as db:
            result = await db.execute(select(Fact).where(Fact.id == fact.id))
            db_fact = result.scalar_one_or_none()
            if db_fact:
                db_fact.verification_status = status_enum
                # Prefer all_source_urls if available, otherwise use web_source_url
                all_urls = verification_data.get("all_source_urls")
                if all_urls is not None and len(all_urls) > 0:
                    db_fact.web_source_url = "\n".join(all_urls)
                elif verification_data.get("web_source_url"):
                    db_fact.web_source_url = verification_data.get("web_source_url")
                else:
                    db_fact.web_source_url = None
                db_fact.confidence_score = verification_data["confidence_score"]
                db_fact.verification_reasoning = verification_data["verification_reasoning"]
                await db.commit()

    async def _update_fact_from_cache(self, fact: Fact, cached_result: dict) -> None:
        """Update fact from cached verification result."""
        async with db_manager.session() as db:
            result = await db.execute(select(Fact).where(Fact.id == fact.id))
            db_fact = result.scalar_one_or_none()
            if db_fact:
                db_fact.verification_status = VerificationStatus[cached_result["verification_status"]]
                # Prefer all_source_urls if available, otherwise use web_source_url
                all_urls = cached_result.get("all_source_urls")
                if all_urls is not None and len(all_urls) > 0:
                    db_fact.web_source_url = "\n".join(all_urls)
                elif cached_result.get("web_source_url"):
                    db_fact.web_source_url = cached_result.get("web_source_url")
                else:
                    db_fact.web_source_url = None
                db_fact.confidence_score = cached_result.get("confidence_score", 0.5)
                db_fact.verification_reasoning = cached_result.get("verification_reasoning")
                await db.commit()

    async def _get_web_search_setting(self, document_id) -> bool:
        """Get web_search_enabled setting for document."""
        async with db_manager.session() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document:
                return document.web_search_enabled
        return True  # Default to enabled

    async def _mark_facts_pending(self, facts: list[Fact]) -> None:
        """Mark all facts as pending when web search is disabled."""
        async with db_manager.session() as db:
            for fact in facts:
                fact.verification_status = VerificationStatus.PENDING
                fact.confidence_score = 0.0
                fact.verification_reasoning = "Web search disabled for this document"
                fact.web_source_url = None
                db.add(fact)
            await db.commit()

    @classmethod
    def from_settings(cls, settings) -> 'WebVerificationStage':
        """Create WebVerificationStage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="web_verification",
            document_state=DocumentProcessingState.WEB_VERIFICATION,
            message_state=ProcessingState.WEB_VERIFICATION,
            cache_enabled=True,
            custom_params={
                "web_search_enabled": True,
                "max_search_results": 5,
                "index_verified_sources": True
            }
        )
        return cls(config)
