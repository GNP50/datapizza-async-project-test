"""
Response generation utilities.

Handles generating responses using:
1. Conversation history (so the user can have a real dialog)
2. Semantic cache (pre-generated Q&A pairs from facts)
3. RAG fallback (raw document chunks)
4. Sources attribution (verification URLs)
5. Deep mode (full document content from storage)
"""
import logging
from uuid import UUID

from app.models.document import Document
from app.models.message import Message, MessageRole
from app.services.database import db_manager
from app.services.llm import llm_client
from app.services.rag import document_processor, semantic_cache
from app.services.storage import storage_manager
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Maximum number of previous messages to include for conversational context
MAX_HISTORY_MESSAGES = 10


async def _get_conversation_history(chat_id: UUID, exclude_message_id: UUID) -> list[dict]:
    """Fetch recent conversation history for this chat."""
    async with db_manager.session() as db:
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .where(Message.id != exclude_message_id)
            .where(Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]))
            .order_by(Message.created_at.desc())
            .limit(MAX_HISTORY_MESSAGES)
        )
        messages = result.scalars().all()

    # Reverse to chronological order
    messages = list(reversed(messages))
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in messages
    ]


def _format_conversation_history(history: list[dict]) -> str:
    """Format conversation history for inclusion in prompts."""
    if not history:
        return ""
    lines = []
    for msg in history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['content']}")
    return "\n".join(lines)


def _format_sources(cached_results: list) -> list[str]:
    """Extract unique verification sources from cached QA results."""
    sources = []
    seen_urls = set()
    for result in cached_results:
        meta = result.metadata or {}
        url = meta.get("web_source_url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append(url)
    return sources


async def _verify_sources_used(
    query: str,
    answer: str,
    available_sources: list[str]
) -> list[str]:
    """
    Use LLM to verify which sources were actually used in the answer.

    Args:
        query: User's original question
        answer: Generated answer
        available_sources: List of all available source URLs

    Returns:
        Filtered list of sources that were actually used
    """
    if not available_sources:
        return []

    if len(available_sources) == 1:
        # If only one source, assume it was used
        return available_sources

    try:
        # Build source list for LLM
        source_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(available_sources)])

        system_prompt = """You are a source verification expert. Given a question, an answer, and a list of sources, determine which sources were ACTUALLY used to generate the answer.

CRITICAL RULES:
- Return ONLY the source numbers (comma-separated) that contain information that was DIRECTLY used in the answer
- A source is used ONLY if specific facts, data, or information from it appear in the answer
- If a source was available but NOT cited in the answer, exclude it
- If unsure, EXCLUDE the source (be conservative)
- Return ONLY numbers separated by commas, NO explanations, NO extra text

Examples:
Question: "What is the revenue?"
Answer: "According to the financial report, revenue was $5M."
Sources: 1. https://finance.example.com/report, 2. https://news.example.com/article
Output: 1

Question: "What happened in the meeting?"
Answer: "The meeting discussed budget and timeline, referencing both the project plan and status update."
Sources: 1. https://docs.example.com/plan, 2. https://docs.example.com/status, 3. https://wiki.example.com/notes
Output: 1,2"""

        prompt = f"""Question: {query}
Answer: {answer}

Available Sources:
{source_list}

Which sources were actually used to generate this answer? Return only the numbers (comma-separated):"""

        response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
        result_text = response.text.strip()

        logger.info(f"LLM source verification raw response: {result_text}")

        # Parse the response
        try:
            import re
            numbers = re.findall(r'\d+', result_text)
            used_indices = [int(num) - 1 for num in numbers if num.isdigit()]

            # Filter sources
            used_sources = [available_sources[i] for i in used_indices if 0 <= i < len(available_sources)]

            logger.info(f"Source verification: {len(available_sources)} -> {len(used_sources)} sources used")

            # If LLM returns empty, return at least one source to avoid breaking UI
            if not used_sources and available_sources:
                logger.warning("LLM returned no sources, using first source as fallback")
                return [available_sources[0]]

            return used_sources

        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse LLM source verification: '{result_text}', error: {e}")
            return available_sources  # Fallback to all sources on parse error

    except Exception as e:
        logger.error(f"Source verification failed: {e}")
        return available_sources  # Fallback to all sources on error


async def _augment_query(query: str) -> list[str]:
    """
    Use LLM to generate focused query variations for better semantic search.
    Returns a list of augmented queries including the original.

    Strategy: Generate 2-3 high-quality variations instead of 4-5 to reduce noise.
    """
    system_prompt = """You are a query augmentation expert. Given a user query, generate 2-3 HIGH-QUALITY alternative phrasings that capture the EXACT same intent.

RULES:
- Generate ONLY semantically equivalent queries (same meaning, different words)
- DO NOT broaden or narrow the question - keep the exact same scope
- DO NOT ask related but different questions
- Keep each variation concise (1 sentence max)
- Use different vocabulary and sentence structures
- Return ONLY the alternative queries, one per line
- Do NOT include the original query
- Do NOT include numbering or bullet points
- Focus on QUALITY over quantity - 2-3 excellent variations are better than 5 mediocre ones

Example:
Original: "What are the main benefits of solar energy?"
Good variations:
What advantages does solar power offer?
Why is solar energy beneficial?

Bad variations (too different):
How do solar panels work? ← Different question
Is solar energy better than wind? ← Different scope"""

    prompt = f"Original query: {query}\n\nGenerate 2-3 semantically equivalent alternative queries:"

    try:
        response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
        variations = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        # Always include the original query first, then top 2-3 variations
        return [query] + variations[:3]  # Max 4 total (original + 3 variations)
    except Exception as e:
        logger.warning(f"Query augmentation failed: {e}, using original query only")
        return [query]


async def _select_best_documents(
    query: str,
    search_results: list,
    documents: list[Document],
    max_documents: int = 3
) -> list[UUID]:
    """
    Select the most relevant documents from search results using a hybrid scoring approach.
    Returns list of document IDs ranked by relevance.

    Simplified approach: Use score aggregation instead of LLM for faster and more reliable selection.
    """
    if not search_results:
        return []

    # Group results by document_id and calculate hybrid scores
    doc_scores = {}
    doc_info = {}

    for result in search_results:
        metadata = result.metadata or {}
        doc_id = metadata.get("document_id")
        if not doc_id:
            continue

        # Aggregate scores per document
        score = getattr(result, 'score', 0.0)
        if doc_id not in doc_scores:
            doc_scores[doc_id] = []
            doc_info[doc_id] = {
                "filename": metadata.get("filename", "Unknown"),
            }
        doc_scores[doc_id].append(score)

    # Calculate hybrid score per document
    # Combines: max score (best single match), avg score (overall relevance), num matches (coverage)
    doc_rankings = []
    for doc_id, scores in doc_scores.items():
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        num_matches = len(scores)

        # Hybrid score: weight max score more (best match matters most)
        # but also consider average and number of matches
        hybrid_score = (
            max_score * 0.5 +           # Best match is most important
            avg_score * 0.3 +            # Overall relevance
            min(num_matches / 10, 0.2)   # Number of matches (capped at 0.2)
        )

        doc_rankings.append({
            "id": doc_id,
            "hybrid_score": hybrid_score,
            "max_score": max_score,
            "avg_score": avg_score,
            "num_matches": num_matches,
            "filename": doc_info[doc_id]["filename"]
        })

    # Sort by hybrid score (descending)
    doc_rankings.sort(key=lambda x: x["hybrid_score"], reverse=True)

    # Select top documents
    selected_docs = doc_rankings[:max_documents]
    selected_ids = [UUID(doc["id"]) for doc in selected_docs]

    logger.info(
        f"Selected {len(selected_ids)} documents by hybrid scoring: "
        f"{[f'{doc['filename']} (score={doc['hybrid_score']:.2f})' for doc in selected_docs]}"
    )

    return selected_ids


async def _load_full_documents(document_ids: list[UUID], documents: list[Document]) -> dict[UUID, str]:
    """
    Load full document content from storage for deep mode.
    Returns dict mapping document_id -> full_text
    """
    doc_map = {doc.id: doc for doc in documents}
    full_contents = {}

    for doc_id in document_ids:
        doc = doc_map.get(doc_id)
        if not doc:
            logger.warning(f"Document {doc_id} not found in documents list")
            continue

        try:
            # Load the .md file from storage
            md_path = doc.file_path.replace(doc.filename, f"{doc.id}.md")
            logger.info(f"Loading full content from: {md_path}")
            content_bytes = await storage_manager.download(md_path)
            full_text = content_bytes.decode("utf-8")
            full_contents[doc_id] = full_text
            logger.info(f"Loaded {len(full_text)} chars from {doc.filename}")
        except Exception as e:
            logger.error(f"Failed to load full content for document {doc_id} ({doc.filename}): {e}")

    return full_contents


def _extract_relevant_documents(cached_results: list, documents: list) -> list[dict]:
    """Extract only the documents that actually contributed to the response.
    Maps document_id from cache/search results back to the document objects."""
    doc_map = {str(doc.id): doc for doc in documents}
    relevant_ids = set()
    for result in cached_results:
        meta = result.metadata or {} if hasattr(result, 'metadata') else {}
        doc_id = meta.get("document_id")
        if doc_id:
            relevant_ids.add(doc_id)

    relevant_docs = []
    for doc_id in relevant_ids:
        doc = doc_map.get(doc_id)
        if doc:
            relevant_docs.append({"id": str(doc.id), "filename": doc.filename})
    return relevant_docs


async def _verify_document_relevance(
    query: str,
    answer: str,
    documents_used: list[dict],
    threshold: float = 0.7
) -> list[dict]:
    """
    Use LLM to verify which documents are actually relevant to the answer.
    Returns filtered list of documents that are truly relevant.

    Args:
        query: User's original question
        answer: Generated answer
        documents_used: List of document dicts with 'id' and 'filename'
        threshold: Minimum confidence threshold (0-1)

    Returns:
        Filtered list of relevant documents
    """
    if not documents_used or len(documents_used) <= 1:
        # If 0 or 1 document, no need to filter - that document is assumed relevant
        return documents_used

    try:
        # Build document list for LLM
        doc_list = "\n".join([f"{i+1}. {doc['filename']}" for i, doc in enumerate(documents_used)])

        system_prompt = """You are a strict document relevance evaluator. Given a user question, an answer, and a list of documents, determine which documents were ACTUALLY used to answer the question.

CRITICAL RULES:
- Return ONLY the document numbers (comma-separated) that contain information that was DIRECTLY used in the answer
- A document is relevant ONLY if specific facts, data, or information from it appear in the answer
- If a document was loaded but NOT used, exclude it
- If a document is merely related but not cited, exclude it
- If unsure, EXCLUDE the document (be conservative, not generous)
- Return ONLY numbers separated by commas, NO explanations, NO extra text

Examples:
Question: "What is the revenue for Q1?"
Answer: "According to the financial report, Q1 revenue was $5M"
Documents: 1. financial_report.pdf, 2. marketing_plan.pdf, 3. legal_docs.pdf
Output: 1

Question: "What are the company's values?"
Answer: "The company values innovation, integrity, and customer focus, as outlined in the handbook and demonstrated in recent initiatives."
Documents: 1. employee_handbook.pdf, 2. quarterly_report.pdf, 3. strategy_deck.pdf
Output: 1,3

Question: "What is the project timeline?"
Answer: "The project timeline is Q1 2024 to Q3 2024."
Documents: 1. project_plan.pdf, 2. budget.pdf, 3. team_roster.pdf
Output: 1"""

        prompt = f"""Question: {query}
Answer: {answer}

Documents:
{doc_list}

Which documents were actually used to generate this answer? Return only the numbers (comma-separated):"""

        response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
        result_text = response.text.strip()

        logger.info(f"LLM document relevance raw response: {result_text}")

        # Parse the response - extract all digits (handles "1,2,3" or "1, 2, 3" or "1 2 3")
        try:
            import re
            # Extract all numbers from the response
            numbers = re.findall(r'\d+', result_text)
            relevant_indices = [int(num) - 1 for num in numbers if num.isdigit()]

            # Filter documents
            filtered = [documents_used[i] for i in relevant_indices if 0 <= i < len(documents_used)]

            logger.info(f"LLM document filter: {len(documents_used)} -> {len(filtered)} documents (indices: {relevant_indices})")

            # If LLM returns empty, it means NO documents are relevant (not all documents)
            # This is a critical fix - empty response should mean empty result, not fallback
            if not filtered:
                logger.warning(f"LLM returned no relevant documents for query. Raw response: {result_text}")
                # Return at least one document to avoid breaking the UI
                return [documents_used[0]] if documents_used else []

            return filtered

        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse LLM document relevance result: '{result_text}', error: {e}")
            return documents_used  # Fallback to original list on parsing error

    except Exception as e:
        logger.error(f"Document relevance verification failed: {e}")
        return documents_used  # Fallback to original list on error


async def _detect_language_from_documents(documents: list[Document], chat_id: UUID) -> str:
    """
    Detect the primary language from document content.
    Returns ISO language code (e.g., 'it', 'en', 'es', 'fr').
    """
    try:
        # Sample text from multiple documents using a generic query
        sample_texts = []
        generic_queries = ["summary", "information", "content"]  # Generic words likely to match

        for doc in documents[:3]:  # Check up to 3 documents
            for query in generic_queries:
                try:
                    doc_context, _ = await document_processor.search_relevant_context(
                        query=query,
                        chat_id=chat_id,
                        document_id=doc.id,
                        limit=1
                    )
                    if doc_context and len(doc_context.strip()) > 50:
                        # Remove the "[From 'filename']" or "[Context N]" prefix
                        cleaned = doc_context.split("]", 1)[-1].strip()
                        sample_texts.append(cleaned[:800])  # Take first 800 chars
                        break  # Got text for this doc, move to next
                except Exception as e:
                    logger.debug(f"Failed to get context for doc {doc.id} with query '{query}': {e}")
                    continue

        if not sample_texts:
            logger.warning("No text samples found for language detection, defaulting to English")
            return "en"  # Default to English

        combined_text = " ".join(sample_texts)[:2000]  # Limit total text

        # Use LLM to detect language
        system_prompt = """You are a language detection expert. Analyze the text and return ONLY the ISO 639-1 language code (2 letters).
Examples: 'it' for Italian, 'en' for English, 'es' for Spanish, 'fr' for French, 'de' for German.
Return ONLY the 2-letter code, nothing else."""

        prompt = f"Detect the language of this text:\n\n{combined_text}"

        response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
        detected_lang = response.text.strip().lower()[:2]

        # Validate it's a 2-letter code
        if len(detected_lang) == 2 and detected_lang.isalpha():
            logger.info(f"Detected language: {detected_lang}")
            return detected_lang

        return "en"  # Default fallback

    except Exception as e:
        logger.warning(f"Language detection failed: {e}, defaulting to English")
        return "en"


async def generate_response(message_id: UUID, documents: list[Document], bypass_cache: bool = False) -> tuple[str, dict]:
    """
    Generate response using a multi-tier strategy:
    1. Semantic cache lookup (fast, pre-generated Q&A) - unless bypass_cache=True
    2. RAG with enhanced retrieval:
       - Normal mode (bypass_cache=False): Query augmentation + document selection + filtered vector search
       - Deep mode (bypass_cache=True): Query augmentation + document selection + full document loading
    3. Conversational fallback (no documents)

    Always includes conversation history for dialog continuity.

    Args:
        message_id: The message to respond to
        documents: Available documents for context
        bypass_cache: If True, use deep mode (full documents) instead of semantic cache + chunks

    Returns:
        tuple[str, dict]: (response_text, metadata) where metadata includes:
            - cached: bool - whether response used vector store cache (False in deep mode)
            - response_type: str - "cached", "rag", "rag_deep", or "conversational"
            - documents_used: list[dict] - documents used in generation
            - cache_score: float - confidence score if cached
    """
    try:
        async with db_manager.session() as db:
            result = await db.execute(select(Message).where(Message.id == message_id))
            message = result.scalar_one_or_none()
            if not message:
                return "Message not found", {"cached": False, "response_type": "error", "documents_used": []}

            content = message.content
            chat_id = message.chat_id

        # Check if user uploaded documents without a question
        if (not content or content.strip() == "") and documents:
            logger.info("User uploaded documents without a question, generating automatic summary")

            # Detect language from documents
            detected_lang = await _detect_language_from_documents(documents, chat_id)

            # Create language-specific prompt for summary
            doc_names = ", ".join([f"'{d.filename}'" for d in documents[:10]])
            prompts_by_lang = {
                "it": f"Riassumi i seguenti documenti caricati: {doc_names}. Evidenzia i punti chiave, i temi principali e le informazioni più importanti.",
                "en": f"Summarize the following uploaded documents: {doc_names}. Highlight key points, main themes, and the most important information.",
                "es": f"Resume los siguientes documentos cargados: {doc_names}. Destaca los puntos clave, los temas principales y la información más importante.",
                "fr": f"Résumez les documents suivants: {doc_names}. Mettez en évidence les points clés, les thèmes principaux et les informations les plus importantes.",
                "de": f"Fassen Sie die folgenden hochgeladenen Dokumente zusammen: {doc_names}. Heben Sie wichtige Punkte, Hauptthemen und die wichtigsten Informationen hervor."
            }

            # Use detected language or default to English
            content = prompts_by_lang.get(detected_lang, prompts_by_lang["en"])
            logger.info(f"Auto-generated prompt in language '{detected_lang}': {content[:100]}...")

        # Get conversation history for context
        history = await _get_conversation_history(chat_id, message_id)
        history_text = _format_conversation_history(history)

        # --- Tier 1: Semantic cache (Q&A pairs from verified facts) ---
        all_cached_results = []
        if documents:
            for doc in documents:
                cached_results = await semantic_cache.search_cache(
                    query=content,
                    chat_id=chat_id,
                    document_id=doc.id,
                    top_k=5,
                    min_score=0.70  # Lowered from 0.90 to increase cache hit rate
                )
                all_cached_results.extend(cached_results)

        # Also search across entire chat (catches cross-document questions)
        chat_wide_results = await semantic_cache.search_cache(
            query=content,
            chat_id=chat_id,
            top_k=5,
            min_score=0.55  # Lowered from 0.65 for better coverage
        )
        # Merge and deduplicate
        seen_questions = {r.question for r in all_cached_results}
        for r in chat_wide_results:
            if r.question not in seen_questions:
                all_cached_results.append(r)
                seen_questions.add(r.question)

        # Sort by score
        all_cached_results.sort(key=lambda x: x.score, reverse=True)

        if not bypass_cache and all_cached_results and all_cached_results[0].score >= 0.65:  # Lowered from 0.75
            # High-confidence cache hit — use LLM to synthesize a natural answer
            # from multiple cached results + conversation history
            logger.info(f"Semantic cache hit! Top score: {all_cached_results[0].score:.2f}, {len(all_cached_results)} results")
            response = await _synthesize_from_cache(content, all_cached_results, history_text)
            documents_used = _extract_relevant_documents(all_cached_results, documents) if documents else []
            metadata = {
                "cached": True,
                "response_type": "cached",
                "documents_used": documents_used,
                "cache_score": all_cached_results[0].score
            }
            return response, metadata

        # --- Tier 2: RAG with enhanced retrieval ---
        if documents:
            # Determine mode based on bypass_cache
            use_deep_mode = bypass_cache
            mode_label = "DEEP MODE" if use_deep_mode else "NORMAL MODE"
            logger.info(f"Semantic cache miss or bypassed, using RAG {mode_label}")

            response, rag_doc_ids = await _generate_rag_response(
                content,
                chat_id,
                documents,
                history_text,
                all_cached_results,
                use_deep_mode=use_deep_mode
            )

            # Build documents_used list from RAG selected documents
            # These are the documents actually used to generate the response
            doc_map = {str(doc.id): doc for doc in documents}
            documents_used = []
            seen_ids = set()

            # Primary sources: documents selected and used by RAG
            for doc_id in rag_doc_ids:
                if doc_id not in seen_ids:
                    doc = doc_map.get(doc_id)
                    if doc:
                        documents_used.append({"id": str(doc.id), "filename": doc.filename})
                        seen_ids.add(doc_id)

            # Optional: Add documents from partial cache hits only if they're not already included
            # This ensures we don't miss any document that contributed via cache
            for extra in _extract_relevant_documents(all_cached_results, documents):
                if extra["id"] not in seen_ids:
                    documents_used.append(extra)
                    seen_ids.add(extra["id"])

            # CRITICAL: Use LLM to verify document relevance
            # This ensures we only show documents that truly contributed to the answer
            # In deep mode especially, we load full documents but may only use content from some of them
            if len(documents_used) > 1 or use_deep_mode:
                try:
                    documents_used = await _verify_document_relevance(
                        query=content,
                        answer=response,
                        documents_used=documents_used
                    )
                    logger.info(f"Applied LLM document relevance filter: {len(documents_used)} documents remaining")
                except Exception as e:
                    logger.warning(f"Document relevance filtering failed, using all documents: {e}")

            metadata = {
                "cached": False,  # Deep mode doesn't use vector store cache
                "response_type": "rag_deep" if use_deep_mode else "rag",
                "documents_used": documents_used,
                "cache_score": all_cached_results[0].score if all_cached_results else 0.0
            }
            return response, metadata

        # --- Tier 3: Conversational fallback (no documents at all) ---
        logger.info("No documents, using conversational mode")
        response = await _generate_conversational_response(content, history_text)
        metadata = {
            "cached": False,
            "response_type": "conversational",
            "documents_used": [],
            "cache_score": 0.0
        }
        return response, metadata

    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        error_metadata = {
            "cached": False,
            "response_type": "error",
            "documents_used": [],
            "cache_score": 0.0
        }
        return f"I'm processing your request but encountered an issue: {str(e)}", error_metadata


async def _synthesize_from_cache(
    query: str,
    cached_results: list,
    history_text: str
) -> str:
    """Synthesize a natural response from multiple semantic cache hits."""
    # Build context from cached Q&A pairs with document attribution
    qa_context_parts = []
    for r in cached_results:
        meta = r.metadata or {}
        filename = meta.get("filename", "")
        source_label = f" [from '{filename}']" if filename else ""
        qa_context_parts.append(f"Q: {r.question}\nA: {r.answer}{source_label} (confidence: {r.score:.0%})")
    qa_context = "\n\n".join(qa_context_parts)

    sources = _format_sources(cached_results)

    system_prompt = """You are a helpful AI assistant that answers questions based on the user's uploaded documents.

RULES:
- Answer the user's question naturally using the provided verified information.
- Synthesize information from multiple sources if relevant — don't just repeat one answer.
- When information comes from specific documents (indicated by [from 'filename']), mention which document it comes from in your answer.
- If the conversation history is relevant, maintain continuity (e.g., refer back to previous topics).
- Be thorough but concise.
- NEVER say you cannot access or read the documents — the content has already been extracted and provided to you.
- DO NOT mention "cached answers", "Q&A pairs", or any internal system details.
- Answer in the same language as the user's question.
- Speak as a knowledgeable assistant who has read the documents."""

    prompt_parts = []
    if history_text:
        prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}\n")
    prompt_parts.append(f"VERIFIED INFORMATION:\n{qa_context}\n")
    prompt_parts.append(f"USER QUESTION: {query}")

    prompt = "\n".join(prompt_parts)

    response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
    answer = response.text.strip()

    # Verify which sources were actually used in the answer
    if sources:
        verified_sources = await _verify_sources_used(query, answer, sources)
        if verified_sources:
            sources_text = "\n".join([f"- {url}" for url in verified_sources])
            answer += f"\n\nSources:\n{sources_text}"

    return answer


async def _generate_rag_response(
    query: str,
    chat_id: UUID,
    documents: list[Document],
    history_text: str,
    partial_cache_results: list,
    use_deep_mode: bool = False
) -> tuple[str, list[str]]:
    """
    RAG-based response generation with document chunks or full documents.

    Strategy:
    1. Query augmentation: Generate multiple query variations
    2. Broad search: Search with all variations across vector store
    3. Document selection: LLM selects best documents
    4. Filtered retrieval:
       - Normal mode: Re-search vector store filtered by selected document_ids
       - Deep mode: Load full document content from storage
    5. Generate response

    Args:
        query: User query
        chat_id: Chat ID for isolation
        documents: Available documents
        history_text: Conversation history
        partial_cache_results: Any partial cache hits
        use_deep_mode: If True, load full documents instead of chunks

    Returns:
        tuple[str, list[str]]: (response_text, list_of_relevant_document_ids)
    """
    processed_docs = [d for d in documents if d.processed]
    logger.info(f"RAG: searching {len(processed_docs)} processed documents for query: {query[:100]}... (deep_mode={use_deep_mode})")

    # Step 1: Query Augmentation
    augmented_queries = await _augment_query(query)
    logger.info(f"RAG: generated {len(augmented_queries)} query variations")

    # Step 2: Broad search with all query variations
    all_search_results = []
    for q in augmented_queries:
        try:
            from app.services.rag.vectorstore import vectorstore
            results = await vectorstore.a_search(
                q,
                chat_id=chat_id,
                top_k=8,
                filter=None  # No document filter for initial broad search
            )
            all_search_results.extend(results)
            logger.debug(f"RAG: query '{q[:60]}...' returned {len(results)} results")
        except Exception as e:
            logger.error(f"RAG: search failed for query variation '{q[:60]}...': {e}")

    # Deduplicate results by chunk ID
    seen_ids = set()
    unique_results = []
    for result in all_search_results:
        chunk_id = getattr(result, 'id', None) or id(result)
        if chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            unique_results.append(result)

    logger.info(f"RAG: collected {len(unique_results)} unique results from augmented search")

    if not unique_results:
        logger.warning("RAG: no search results found, cannot proceed with document selection")
        # Fallback to simple response
        return await _generate_simple_rag_fallback(query, chat_id, documents, history_text, partial_cache_results)

    # Step 3: LLM selects best documents
    selected_doc_ids = await _select_best_documents(query, unique_results, documents, max_documents=3)
    logger.info(f"RAG: selected {len(selected_doc_ids)} documents: {selected_doc_ids}")

    if not selected_doc_ids:
        logger.warning("RAG: no documents selected, using fallback")
        return await _generate_simple_rag_fallback(query, chat_id, documents, history_text, partial_cache_results)

    # Step 4: Retrieve context based on mode
    if use_deep_mode:
        # Deep mode: Load full document content from storage
        logger.info("RAG: DEEP MODE - Loading full document content from storage")
        full_docs = await _load_full_documents(selected_doc_ids, documents)

        if not full_docs:
            logger.error("RAG: Failed to load any full documents in deep mode")
            return await _generate_simple_rag_fallback(query, chat_id, documents, history_text, partial_cache_results)

        # Build context from full documents
        doc_map = {doc.id: doc for doc in documents}
        context_parts = []
        relevant_doc_ids = []

        for doc_id, full_text in full_docs.items():
            doc = doc_map.get(doc_id)
            if doc:
                context_parts.append(f"[Complete document: '{doc.filename}']\n{full_text}")
                relevant_doc_ids.append(str(doc_id))

        rag_context = "\n\n---\n\n".join(context_parts)
        logger.info(f"RAG DEEP MODE: using {len(full_docs)} full documents ({len(rag_context)} chars total)")

    else:
        # Normal mode: Re-search vector store filtered by selected document IDs
        logger.info("RAG: NORMAL MODE - Re-searching vector store with document filters")
        context_parts = []
        relevant_doc_ids = []

        for doc_id in selected_doc_ids:
            try:
                # Search again but now filtered to this specific document
                doc_context, _ = await document_processor.search_relevant_context(
                    query=query,  # Use original query for final retrieval
                    chat_id=chat_id,
                    document_id=doc_id,
                    limit=5,
                    min_score=0.15  # Lowered from 0.2 for better recall
                )
                if doc_context:
                    context_parts.append(doc_context)
                    relevant_doc_ids.append(str(doc_id))
                    doc = next((d for d in documents if d.id == doc_id), None)
                    logger.info(f"RAG: retrieved context from '{doc.filename if doc else doc_id}'")
            except Exception as e:
                logger.error(f"RAG: filtered search failed for document {doc_id}: {e}")

        rag_context = "\n\n".join(context_parts) if context_parts else ""
        logger.info(f"RAG NORMAL MODE: retrieved {len(context_parts)} contexts ({len(rag_context)} chars total)")

    # Also include any partial cache hits for enrichment
    cache_context = ""
    if partial_cache_results:
        cache_context = "\n\n".join([
            f"Related verified fact: {r.answer}"
            for r in partial_cache_results
        ])

    # Build document list for context
    doc_list = ", ".join([f"'{d.filename}'" for d in processed_docs]) if processed_docs else "none"

    mode_instruction = "You have access to the COMPLETE content of the selected documents." if use_deep_mode else "You have access to relevant sections from the selected documents."

    system_prompt = f"""You are a helpful AI assistant that answers questions based on the user's uploaded documents.
The following documents have been uploaded and analyzed: {doc_list}.

{mode_instruction}

RULES:
- Use the provided DOCUMENT CONTEXT to answer the user's question accurately.
- The context is labeled with [From 'filename'] or [Complete document: 'filename'] to indicate which document each piece of information comes from.
- If verified facts are also provided, prefer them as they have been cross-checked.
- Maintain conversation continuity when history is provided.
- If the provided context does not contain enough information to fully answer, say what you can based on what is available and note what is missing.
- NEVER say you cannot access or read the documents — the document content has already been extracted and provided to you below.
- Be thorough but concise.
- DO NOT mention internal system details like "RAG", "chunks", "vector store", "semantic cache", or "deep mode"."""

    prompt_parts = []
    if history_text:
        prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}\n")
    if cache_context:
        prompt_parts.append(f"VERIFIED FACTS (cross-checked):\n{cache_context}\n")
    if rag_context:
        prompt_parts.append(f"DOCUMENT CONTEXT:\n{rag_context}\n")
    else:
        prompt_parts.append("DOCUMENT CONTEXT:\nNo relevant sections were found for this specific query. Try to answer based on the conversation history and verified facts if available.\n")
    prompt_parts.append(f"USER QUESTION: {query}")

    prompt = "\n".join(prompt_parts)

    logger.info(f"RAG: sending prompt to LLM ({len(prompt)} chars, context: {len(rag_context)} chars)")

    response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
    answer = response.text.strip()

    # Verify which sources were actually used in the answer
    sources = _format_sources(partial_cache_results)
    if sources:
        verified_sources = await _verify_sources_used(query, answer, sources)
        if verified_sources:
            sources_text = "\n".join([f"- {url}" for url in verified_sources])
            answer += f"\n\nSources:\n{sources_text}"

    return answer, relevant_doc_ids


async def _generate_simple_rag_fallback(
    query: str,
    chat_id: UUID,
    documents: list[Document],
    history_text: str,
    partial_cache_results: list
) -> tuple[str, list[str]]:
    """
    Fallback RAG when advanced strategies fail.
    Uses simple broad search across all documents.
    """
    logger.info("RAG: Using simple fallback strategy")
    context_parts = []
    relevant_doc_ids = []

    try:
        broad_context, matched_ids = await document_processor.search_relevant_context(
            query=query,
            chat_id=chat_id,
            document_id=None,
            limit=8,
            min_score=0.15
        )
        if broad_context:
            context_parts.append(broad_context)
            relevant_doc_ids.extend(matched_ids)
    except Exception as e:
        logger.error(f"RAG fallback: search failed: {e}")

    rag_context = "\n\n".join(context_parts) if context_parts else ""
    cache_context = ""
    if partial_cache_results:
        cache_context = "\n\n".join([f"Related verified fact: {r.answer}" for r in partial_cache_results])

    processed_docs = [d for d in documents if d.processed]
    doc_list = ", ".join([f"'{d.filename}'" for d in processed_docs]) if processed_docs else "none"

    system_prompt = f"""You are a helpful AI assistant that answers questions based on the user's uploaded documents.
The following documents have been uploaded and analyzed: {doc_list}.

RULES:
- Use the provided DOCUMENT CONTEXT to answer the user's question accurately.
- If verified facts are provided, prefer them as they have been cross-checked.
- Maintain conversation continuity when history is provided.
- If the provided context does not contain enough information to fully answer, say what you can based on what is available.
- NEVER say you cannot access or read the documents.
- Be thorough but concise."""

    prompt_parts = []
    if history_text:
        prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}\n")
    if cache_context:
        prompt_parts.append(f"VERIFIED FACTS:\n{cache_context}\n")
    if rag_context:
        prompt_parts.append(f"DOCUMENT CONTEXT:\n{rag_context}\n")
    else:
        prompt_parts.append("DOCUMENT CONTEXT:\nNo relevant sections were found.\n")
    prompt_parts.append(f"USER QUESTION: {query}")

    prompt = "\n".join(prompt_parts)

    response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
    answer = response.text.strip()

    # Verify which sources were actually used in the answer
    sources = _format_sources(partial_cache_results)
    if sources:
        verified_sources = await _verify_sources_used(query, answer, sources)
        if verified_sources:
            sources_text = "\n".join([f"- {url}" for url in verified_sources])
            answer += f"\n\nSources:\n{sources_text}"

    return answer, relevant_doc_ids


async def _generate_conversational_response(query: str, history_text: str) -> str:
    """Pure conversational mode when no documents are available."""
    system_prompt = """You are a helpful AI assistant.
No documents have been uploaded in this conversation yet.

RULES:
- Answer the user's question conversationally and helpfully.
- If the user asks about specific documents or content that requires uploaded files, suggest they upload documents (PDF, images, text files).
- Maintain conversation continuity when history is provided.
- Be concise and friendly.
- Answer in the same language as the user's message."""

    prompt_parts = []
    if history_text:
        prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}\n")
    prompt_parts.append(f"USER: {query}")

    prompt = "\n".join(prompt_parts)

    response = await llm_client.a_invoke(input=prompt, system_prompt=system_prompt)
    return response.text.strip()
