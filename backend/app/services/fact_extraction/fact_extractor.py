"""
Fact Extraction Service - Uses LLM to extract atomic facts from document text.
Organizes facts with page references and logical structure.
"""
from dataclasses import dataclass
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    """A single atomic fact extracted from document"""
    content: str
    page_number: Optional[int] = None
    category: Optional[str] = None  # e.g., "statistic", "claim", "definition"
    confidence: float = 1.0


@dataclass
class FactExtractionResult:
    """Result from fact extraction operation"""
    facts: list[ExtractedFact]
    total_facts: int
    extraction_method: str


class FactExtractor:
    """
    Service for extracting atomic facts from document text using LLM.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def extract_facts(
        self,
        text: str,
        pages: Optional[list[dict]] = None,
        max_facts: int = 50
    ) -> FactExtractionResult:
        """
        Extract atomic facts from document text.

        Args:
            text: Full document text
            pages: Optional list of page data with {page_number, text}
            max_facts: Maximum number of facts to extract

        Returns:
            FactExtractionResult with extracted facts
        """
        try:
            if not self.llm_client:
                # Import here to avoid circular dependency
                from app.services.llm import llm_client
                self.llm_client = llm_client

            # Extract facts using LLM
            facts = await self._extract_with_llm(text, pages, max_facts)

            return FactExtractionResult(
                facts=facts,
                total_facts=len(facts),
                extraction_method="llm"
            )
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            raise RuntimeError(f"Fact extraction failed: {str(e)}") from e

    async def _extract_with_llm(
        self,
        text: str,
        pages: Optional[list[dict]],
        max_facts: int
    ) -> list[ExtractedFact]:
        """Extract facts using LLM"""

        system_prompt = """You are a precision fact-extraction engine. Your job is to decompose document text into atomic, independently verifiable claims.

EXTRACTION RULES:
1. Each fact MUST be a single, self-contained claim that can be verified independently without any surrounding context.
2. Each fact MUST be a complete sentence — never a fragment. Include the subject explicitly (e.g., "The company X reported…" not "Reported…").
3. Numerical data: always include the unit, time period, and entity (e.g., "Apple's revenue in Q3 2024 was $85.8 billion" not "Revenue was $85.8B").
4. Definitions: state the term and the full definition (e.g., "Machine learning is a subset of AI that…").
5. Processes/procedures: describe ONE step or ONE relationship per fact.
6. DO NOT extract opinions, subjective assessments, or speculative language ("may", "could", "is expected to") unless quoting a named source.
7. DO NOT extract the same information twice — deduplicate aggressively.
8. Preserve the page number where each fact appears. If a fact spans pages, use the page where it starts.

CATEGORIZATION — assign exactly ONE:
- "statistic": quantitative data, numbers, percentages, measurements
- "claim": qualitative assertion about the world that can be checked
- "definition": explanation of a concept, term, or acronym
- "process": a described step, method, or procedure
- "relationship": a stated connection between two entities
- "temporal": dated events, timelines, deadlines
- "other": only if none of the above apply

CONFIDENCE SCORING:
- 1.0: directly quoted or clearly stated with source
- 0.8–0.9: clearly stated without ambiguity
- 0.6–0.7: inferred from context but reasonable
- below 0.6: do not include — skip the fact

OUTPUT FORMAT — respond with ONLY a JSON array, no other text:
[
  {
    "content": "The atomic fact as a complete, self-contained sentence",
    "page_number": 1,
    "category": "statistic|claim|definition|process|relationship|temporal|other",
    "confidence": 0.95
  }
]
"""

        # Prepare the text for extraction
        if pages:
            # Process page by page for better page number tracking
            page_context = "\n\n".join([
                f"--- PAGE {p['page_number']} ---\n{p['text']}"
                for p in pages  # Allow more pages for completeness
            ])
            prompt = f"Extract all atomic, verifiable facts from the following document. Assign each fact the page number where it appears.\n\n{page_context}"
        else:
            # Use full text if pages not available — chunk smartly
            truncated = text  # Generous limit for richer extraction
            prompt = (
                f"Extract all atomic, verifiable facts from the following document. "
                f"Since page boundaries are not marked, set page_number to null.\n\n{truncated}"
            )

        try:
            response = await self.llm_client.a_invoke(
                input=prompt,
                system_prompt=system_prompt
            )

            # Parse the JSON response
            response_text = response.text.strip()

            # Try to extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            facts_data = json.loads(response_text)

            if not isinstance(facts_data, list):
                logger.warning("LLM did not return a list, wrapping in list")
                facts_data = [facts_data] if facts_data else []

            # Convert to ExtractedFact objects
            facts = []
            for item in facts_data[:max_facts]:
                if isinstance(item, dict) and "content" in item:
                    facts.append(ExtractedFact(
                        content=item["content"],
                        page_number=item.get("page_number"),
                        category=item.get("category", "other"),
                        confidence=item.get("confidence", 0.9)
                    ))

            return facts

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Fallback: try to extract facts from plain text
            return await self._fallback_extraction(text)
        except Exception as e:
            logger.error(f"LLM fact extraction failed: {e}")
            return await self._fallback_extraction(text)

    async def _fallback_extraction(self, text: str) -> list[ExtractedFact]:
        """Fallback extraction using simple sentence splitting"""
        logger.info("Using fallback fact extraction")

        # Simple heuristic: split by sentences and take meaningful ones
        sentences = text.replace("\n", " ").split(". ")
        facts = []

        for i, sentence in enumerate(sentences):  # Limit to 20 facts
            sentence = sentence.strip()
            if len(sentence) > 30 and len(sentence) < 500:  # Reasonable length
                facts.append(ExtractedFact(
                    content=sentence + "." if not sentence.endswith(".") else sentence,
                    page_number=None,
                    category="other",
                    confidence=0.5  # Lower confidence for fallback
                ))

        return facts


# Global instance
fact_extractor = FactExtractor()
