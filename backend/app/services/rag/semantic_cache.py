"""
Semantic Cache - Q&A pair indexing for fast retrieval.
Indexes question-answer pairs into Qdrant for semantic search.
"""
from uuid import UUID, uuid4
from typing import Optional
from dataclasses import dataclass
from datapizza.type import Chunk, DenseEmbedding
from .vectorstore import vectorstore
from .embedder import embedder
import logging

logger = logging.getLogger(__name__)


@dataclass
class CachedQA:
    """A cached Q&A pair retrieved from semantic cache"""
    question: str
    answer: str
    score: float
    document_id: Optional[str] = None
    fact_id: Optional[str] = None
    metadata: Optional[dict] = None


class SemanticCache:
    """
    Semantic cache for Q&A pairs.
    Stores question-answer pairs in vector store for fast semantic retrieval.
    """

    def __init__(self, collection_suffix: str = "qa_cache"):
        self.collection_suffix = collection_suffix

    async def index_qa_pairs(
        self,
        qa_pairs: list[dict],
        document_id: UUID,
        chat_id: UUID,
        batch_size: int = 50,
        index_answer_keywords: bool = True
    ) -> int:
        """
        Index Q&A pairs into the semantic cache with chat-level isolation.

        Enhanced indexing strategy:
        1. Index the question (primary)
        2. Optionally index key answer phrases to catch keyword-based queries

        Args:
            qa_pairs: List of Q&A pair dicts with keys: question, answer, fact_id, etc.
            document_id: Document ID these Q&A pairs belong to
            chat_id: Chat ID for isolation - ensures Q&A pairs are only accessible within this chat
            batch_size: Number of pairs to index at once
            index_answer_keywords: If True, also index chunks with answer keywords

        Returns:
            Number of Q&A pairs indexed (may be >len(qa_pairs) if answer keywords are indexed)
        """
        try:
            if not qa_pairs:
                logger.warning("No Q&A pairs to index")
                return 0

            logger.info(f"Starting to index {len(qa_pairs)} Q&A pairs for document {document_id}")

            chunks = []
            for i, qa in enumerate(qa_pairs):
                # Primary chunk: Index the QUESTION for semantic search
                chunk_id = str(uuid4())

                chunk = Chunk(
                    id=chunk_id,
                    text=qa["question"],  # Index on question for matching user queries
                    metadata={
                        "type": "qa_pair",
                        "document_id": str(document_id),
                        "fact_id": str(qa.get("fact_id")) if qa.get("fact_id") else None,
                        "question": qa["question"],
                        "answer": qa["answer"],
                        "confidence": qa.get("confidence", 1.0),
                        "qa_index": i,
                        "primary": True,  # Mark as primary question chunk
                        **(qa.get("metadata", {}))
                    }
                )
                chunks.append(chunk)

                # Optional: Create a secondary chunk with question + answer keywords
                # This helps catch queries that use terminology from the answer
                if index_answer_keywords:
                    answer = qa["answer"]
                    # Extract first sentence or first 150 chars of answer as keywords
                    answer_keywords = answer.split('.')[0] if '.' in answer else answer[:150]

                    # Create hybrid text: question + answer excerpt
                    hybrid_text = f"{qa['question']} {answer_keywords}"

                    hybrid_chunk = Chunk(
                        id=str(uuid4()),
                        text=hybrid_text,
                        metadata={
                            "type": "qa_pair",
                            "document_id": str(document_id),
                            "fact_id": str(qa.get("fact_id")) if qa.get("fact_id") else None,
                            "question": qa["question"],
                            "answer": qa["answer"],
                            "confidence": qa.get("confidence", 1.0) * 0.9,  # Slightly lower confidence
                            "qa_index": i,
                            "primary": False,  # Mark as secondary hybrid chunk
                            **(qa.get("metadata", {}))
                        }
                    )
                    chunks.append(hybrid_chunk)

            logger.info(f"Created {len(chunks)} chunks, generating embeddings...")

            # Generate embeddings for all chunks
            texts = [chunk.text for chunk in chunks]
            embeddings_result = await embedder.a_embed(texts)

            logger.info(f"Generated {len(embeddings_result)} embeddings, attaching to chunks...")

            # Attach embeddings to chunks
            for chunk, embedding_vector in zip(chunks, embeddings_result):
                chunk.embeddings = [DenseEmbedding(name="default", vector=embedding_vector)]

            logger.info(f"Indexing {len(chunks)} chunks into vectorstore...")

            # Index in batches with chat_id for isolation
            total_indexed = 0
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                logger.debug(f"Indexing batch {i//batch_size + 1}: {len(batch)} chunks")
                await vectorstore.a_add(batch, chat_id=chat_id)
                total_indexed += len(batch)

            logger.info(f"Indexed {total_indexed} Q&A pair chunks for document {document_id} in chat {chat_id}")
            return total_indexed

        except Exception as e:
            logger.error(f"Failed to index Q&A pairs: {e}", exc_info=True)
            error_msg = str(e) if str(e) else repr(e)
            raise RuntimeError(f"Q&A indexing failed: {type(e).__name__}: {error_msg}") from e

    async def search_cache(
        self,
        query: str,
        chat_id: UUID,
        document_id: Optional[UUID] = None,
        top_k: int = 3,
        min_score: float = 0.7
    ) -> list[CachedQA]:
        """
        Search the semantic cache for similar questions with chat-level isolation.

        Args:
            query: User's question/query
            chat_id: Chat ID for isolation - only searches within this chat
            document_id: Optional filter by document
            top_k: Number of results to return
            min_score: Minimum similarity score threshold

        Returns:
            List of CachedQA objects (deduplicated by question)
        """
        try:
            filter_dict = {"type": "qa_pair"}
            if document_id:
                filter_dict["document_id"] = str(document_id)

            # Search for similar questions with chat isolation
            # Request more results to account for deduplication
            search_top_k = top_k * 3
            results = await vectorstore.a_search(
                query,
                chat_id=chat_id,
                top_k=search_top_k,
                filter=filter_dict
            )

            # Deduplicate by qa_index (same Q&A from primary and hybrid chunks)
            seen_qa_indices = {}
            cached_qas = []

            for result in results:
                # Extract metadata
                metadata = result.metadata or {}

                # Get score from vectorstore results
                score = getattr(result, 'score', 0.0)

                if score >= min_score:
                    qa_index = metadata.get("qa_index")
                    is_primary = metadata.get("primary", True)

                    # Deduplicate: prefer primary chunks over hybrid chunks
                    if qa_index is not None:
                        if qa_index in seen_qa_indices:
                            # Already seen this Q&A
                            existing = seen_qa_indices[qa_index]
                            # Replace if current is primary and existing is not, OR if current has higher score
                            if (is_primary and not existing["is_primary"]) or (score > existing["score"]):
                                # Remove old entry
                                cached_qas = [qa for qa in cached_qas if qa.metadata.get("qa_index") != qa_index]
                                seen_qa_indices[qa_index] = {"score": score, "is_primary": is_primary}
                            else:
                                # Skip this duplicate
                                continue
                        else:
                            seen_qa_indices[qa_index] = {"score": score, "is_primary": is_primary}

                    cached_qas.append(CachedQA(
                        question=metadata.get("question", result.text),
                        answer=metadata.get("answer", ""),
                        score=score,
                        document_id=metadata.get("document_id"),
                        fact_id=metadata.get("fact_id"),
                        metadata=metadata
                    ))

            # Sort by score and return top_k
            cached_qas.sort(key=lambda x: x.score, reverse=True)
            return cached_qas[:top_k]

        except Exception as e:
            logger.error(f"Semantic cache search failed: {e}")
            return []

    async def clear_cache_for_document(self, document_id: UUID) -> bool:
        """
        Clear all cached Q&A pairs for a specific document.

        Args:
            document_id: Document ID to clear cache for

        Returns:
            True if successful
        """
        try:
            # Note: This requires Qdrant delete functionality
            # For now, we'll just log
            logger.info(f"Cache clear requested for document {document_id}")
            # TODO: Implement delete functionality when available
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False


# Global instance
semantic_cache = SemanticCache()
