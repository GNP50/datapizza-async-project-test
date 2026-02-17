"""
Flashcard Generation Service - Generates study flashcards from verified facts.
Creates front (question/prompt) and back (answer) pairs optimized for learning.
"""
from dataclasses import dataclass
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class FlashcardItem:
    """A single flashcard with front and back"""
    front: str
    back: str
    fact_id: Optional[str] = None
    category: Optional[str] = None
    difficulty: int = 3
    confidence: float = 1.0


@dataclass
class FlashcardGenerationResult:
    """Result from flashcard generation"""
    flashcards: list[FlashcardItem]
    total_cards: int
    generation_method: str


class FlashcardGenerator:
    """
    Service for generating study flashcards from document facts.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def generate_flashcards(
        self,
        facts: list[dict],
        max_cards_per_fact: int = 2,
        document_context: Optional[str] = None
    ) -> FlashcardGenerationResult:
        """
        Generate flashcards from verified facts.

        Args:
            facts: List of fact dictionaries with keys: content, verification_status, etc.
            max_cards_per_fact: Maximum flashcards to generate per fact
            document_context: Optional document context for better card generation

        Returns:
            FlashcardGenerationResult with generated flashcards
        """
        try:
            if not self.llm_client:
                from app.services.llm import llm_client
                self.llm_client = llm_client

            valid_facts = [
                f for f in facts
                if f.get("verification_status") in ["verified", "uncertain", "pending"]
            ]

            if not valid_facts:
                logger.warning("No valid facts to generate flashcards from")
                return FlashcardGenerationResult(
                    flashcards=[],
                    total_cards=0,
                    generation_method="none"
                )

            flashcards = await self._generate_with_llm(
                valid_facts,
                max_cards_per_fact,
                document_context
            )

            return FlashcardGenerationResult(
                flashcards=flashcards,
                total_cards=len(flashcards),
                generation_method="llm"
            )
        except Exception as e:
            logger.error(f"Flashcard generation failed: {e}")
            raise RuntimeError(f"Flashcard generation failed: {str(e)}") from e

    async def _generate_with_llm(
        self,
        facts: list[dict],
        max_cards_per_fact: int,
        document_context: Optional[str]
    ) -> list[FlashcardItem]:
        """Generate flashcards using LLM"""

        system_prompt = """You are an expert educator who creates effective study flashcards.
Your job: given a list of verified facts, generate flashcards optimized for active recall and spaced repetition.

FLASHCARD CREATION RULES:
1. Each flashcard has a FRONT (question/prompt) and BACK (answer).
2. The FRONT should be a clear, specific question or fill-in-the-blank prompt.
3. The BACK should be a concise, complete answer (1-3 sentences max).
4. For each fact, generate 1-2 flashcards with DIFFERENT approaches:
   - A direct recall card ("What is X?", "Define X", "What does X do?")
   - A conceptual card ("Why is X important?", "How does X relate to Y?", "What is the significance of X?")
5. Vary card types: definitions, concepts, dates/numbers, comparisons, cause-effect.
6. Avoid trivial or obvious cards — focus on what's worth memorizing.
7. Make the FRONT specific enough that there's one clear correct answer.

DIFFICULTY LEVELS (1-5):
1 = Basic recall (definitions, simple facts)
2 = Understanding (explanations, descriptions)
3 = Application (how things work, relationships)
4 = Analysis (comparisons, cause-effect)
5 = Synthesis (combining multiple concepts)

CATEGORIES:
- "definition": Term/concept definitions
- "concept": Key ideas and principles
- "statistic": Numbers, dates, measurements
- "process": How things work, steps
- "comparison": Differences and similarities
- "cause_effect": Why things happen

OUTPUT FORMAT — respond with ONLY a JSON array, no other text:
[
  {
    "front": "Clear question or prompt",
    "back": "Concise, complete answer",
    "fact_index": 0,
    "category": "definition",
    "difficulty": 2,
    "confidence": 0.9
  }
]
"""

        facts_text = "\n\n".join([
            f"[Fact {i}] {fact['content']}\n"
            f"  Status: {fact.get('verification_status', 'pending')}\n"
            f"  Source: {fact.get('web_source_url', 'none')}\n"
            f"  Confidence: {fact.get('confidence_score', 'N/A')}"
            for i, fact in enumerate(facts)
        ])

        prompt = f"""Generate up to {max_cards_per_fact} flashcard(s) per fact from the following verified facts:

{facts_text}

Remember: include fact_index for each flashcard so we can trace cards back to their source facts."""

        if document_context:
            prompt += f"\n\nDocument context for better card framing: {document_context}"

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

            card_data = json.loads(response_text)

            if not isinstance(card_data, list):
                card_data = [card_data] if card_data else []

            flashcards = []
            for item in card_data:
                if not isinstance(item, dict) or "front" not in item or "back" not in item:
                    continue

                fact_index = item.get("fact_index")
                fact_id = None
                fact_content = None

                if fact_index is not None and 0 <= fact_index < len(facts):
                    fact_id = facts[fact_index].get("id")
                    fact_content = facts[fact_index].get("content")

                flashcards.append(FlashcardItem(
                    front=item["front"],
                    back=item["back"],
                    fact_id=str(fact_id) if fact_id else None,
                    category=item.get("category", "concept"),
                    difficulty=min(5, max(1, item.get("difficulty", 3))),
                    confidence=item.get("confidence", 0.9),
                ))

            return flashcards

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return await self._fallback_generation(facts)
        except Exception as e:
            logger.error(f"LLM flashcard generation failed: {e}")
            return await self._fallback_generation(facts)

    async def _fallback_generation(self, facts: list[dict]) -> list[FlashcardItem]:
        """Fallback flashcard generation using simple templates"""
        logger.info("Using fallback flashcard generation")

        flashcards = []
        for fact in facts:
            content = fact.get("content", "")

            flashcards.append(FlashcardItem(
                front=f"What do you know about: {content}...?" if len(content) > 100 else f"What do you know about: {content}?",
                back=content,
                fact_id=str(fact.get("id")),
                category="concept",
                difficulty=2,
                confidence=0.5,
            ))

        return flashcards


# Global instance
flashcard_generator = FlashcardGenerator()
