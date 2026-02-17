"""
Q&A Generation Service - Generates question-answer pairs for semantic cache.
Creates potential user questions and ideal answers from verified facts.
"""
from dataclasses import dataclass
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class QAPair:
    """A question-answer pair for semantic cache"""
    question: str
    answer: str
    fact_id: Optional[str] = None
    confidence: float = 1.0
    metadata: Optional[dict] = None


@dataclass
class QAGenerationResult:
    """Result from Q&A generation"""
    qa_pairs: list[QAPair]
    total_pairs: int
    generation_method: str


class QAGenerator:
    """
    Service for generating Q&A pairs from facts for semantic caching.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def generate_qa_pairs(
        self,
        facts: list[dict],
        max_pairs_per_fact: int = 2,
        document_context: Optional[str] = None
    ) -> QAGenerationResult:
        """
        Generate Q&A pairs from verified facts.

        Args:
            facts: List of fact dictionaries with keys: content, verification_status, etc.
            max_pairs_per_fact: Maximum Q&A pairs to generate per fact
            document_context: Optional document context for better question generation

        Returns:
            QAGenerationResult with generated Q&A pairs
        """
        try:
            if not self.llm_client:
                from app.services.llm import llm_client
                self.llm_client = llm_client

            # Filter to only verified or uncertain facts (exclude debunked)
            valid_facts = [
                f for f in facts
                if f.get("verification_status") in ["verified", "uncertain", "pending"]
            ]

            if not valid_facts:
                logger.warning("No valid facts to generate Q&A pairs from")
                return QAGenerationResult(
                    qa_pairs=[],
                    total_pairs=0,
                    generation_method="none"
                )

            qa_pairs = await self._generate_with_llm(
                valid_facts,
                max_pairs_per_fact,
                document_context
            )

            return QAGenerationResult(
                qa_pairs=qa_pairs,
                total_pairs=len(qa_pairs),
                generation_method="llm"
            )
        except Exception as e:
            logger.error(f"Q&A generation failed: {e}")
            raise RuntimeError(f"Q&A generation failed: {str(e)}") from e

    async def _generate_with_llm(
        self,
        facts: list[dict],
        max_pairs_per_fact: int,
        document_context: Optional[str]
    ) -> list[QAPair]:
        """Generate Q&A pairs using LLM"""

        system_prompt = """You are an expert at anticipating how users will ask questions about document content.
Your job: given a list of verified facts (with their verification sources), generate the most likely user questions AND high-quality answers.

QUESTION GENERATION RULES:
1. Write questions as a real user would type them — natural, conversational, sometimes imprecise.
2. For each fact, generate 1-2 questions with DIFFERENT angles:
   - A direct question ("What is X?")
   - A contextual question ("How does X relate to Y?" or "Why is X important?")
3. Questions MUST be answerable from the fact alone — do not assume external knowledge.
4. Vary question starters: what, how, when, why, who, where, is, can, does.

ANSWER GENERATION RULES:
1. Each answer must be SELF-CONTAINED — a reader should understand it without seeing the fact.
2. If the fact has a web verification source, naturally weave it into the answer:
   "According to [source], ..." or "This is supported by information from [source]."
3. Keep answers concise (2-4 sentences max) but complete.
4. Never say "the fact states" or "according to the document" — speak as a knowledgeable assistant.
5. Include the verification status subtly: for uncertain facts, use hedging language ("Based on available information...", "Evidence suggests...").

FACT-TO-QA MAPPING:
- Each Q&A pair MUST include a "fact_index" field (0-based) indicating which fact it came from.
- This is CRITICAL for traceability.

OUTPUT FORMAT — respond with ONLY a JSON array, no other text:
[
  {
    "question": "Natural user question",
    "answer": "Complete, self-contained answer",
    "fact_index": 0,
    "confidence": 0.9
  }
]
"""

        # Prepare facts with full context for Q&A generation
        facts_text = "\n\n".join([
            f"[Fact {i}] {fact['content']}\n"
            f"  Status: {fact.get('verification_status', 'pending')}\n"
            f"  Source: {fact.get('web_source_url', 'none')}\n"
            f"  Confidence: {fact.get('confidence_score', 'N/A')}"
            for i, fact in enumerate(facts)
        ])

        prompt = f"""Generate {max_pairs_per_fact} question-answer pair(s) per fact from the following verified facts:

{facts_text}

Remember: include fact_index for each Q&A pair so we can trace answers back to their source facts."""

        if document_context:
            prompt += f"\n\nDocument context for better question framing: {document_context}"

        try:
            response = await self.llm_client.a_invoke(
                input=prompt,
                system_prompt=system_prompt
            )

            response_text = response.text.strip()

            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            qa_data = json.loads(response_text)

            if not isinstance(qa_data, list):
                qa_data = [qa_data] if qa_data else []

            # Convert to QAPair objects with proper fact mapping
            qa_pairs = []
            for item in qa_data:
                if not isinstance(item, dict) or "question" not in item or "answer" not in item:
                    continue

                # Use fact_index from LLM response for accurate mapping
                fact_index = item.get("fact_index")
                fact_id = None
                fact_content = None
                verification_status = None
                web_source_url = None

                if fact_index is not None and 0 <= fact_index < len(facts):
                    fact_id = facts[fact_index].get("id")
                    fact_content = facts[fact_index].get("content")
                    verification_status = facts[fact_index].get("verification_status")
                    web_source_url = facts[fact_index].get("web_source_url")

                qa_pairs.append(QAPair(
                    question=item["question"],
                    answer=item["answer"],
                    fact_id=str(fact_id) if fact_id else None,
                    confidence=item.get("confidence", 0.9),
                    metadata={
                        "verification_status": verification_status,
                        "web_source_url": web_source_url,
                        "fact_content": fact_content,
                    }
                ))

            return qa_pairs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return await self._fallback_generation(facts)
        except Exception as e:
            logger.error(f"LLM Q&A generation failed: {e}")
            return await self._fallback_generation(facts)

    async def _fallback_generation(self, facts: list[dict]) -> list[QAPair]:
        """Fallback Q&A generation using simple templates"""
        logger.info("Using fallback Q&A generation")

        qa_pairs = []
        for fact in facts:
            content = fact.get("content", "")
            source = fact.get("web_source_url", "")
            source_note = f" (Source: {source})" if source else ""

            qa_pairs.append(QAPair(
                question=f"What information is available about: {content}?",
                answer=f"{content}{source_note}",
                fact_id=str(fact.get("id")),
                confidence=0.5,
                metadata={
                    "verification_status": fact.get("verification_status"),
                    "web_source_url": source,
                    "fact_content": content,
                }
            ))

        return qa_pairs


# Global instance
qa_generator = QAGenerator()
