"""
Chat Indexing Service for Qdrant

Manages semantic search for chat metadata (title + summary) with user isolation.
"""
import logging
from uuid import UUID
from datetime import datetime
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from app.core.config import get_settings
from app.services.rag.embedder import embedder

logger = logging.getLogger(__name__)


class ChatIndexManager:
    """
    Manages Qdrant collection for chat metadata with semantic search capabilities.

    Security: All searches MUST filter by user_id to prevent cross-user data access.
    """

    COLLECTION_NAME = "chat_metadata"

    def __init__(self):
        settings = get_settings()
        qdrant_url = getattr(settings, "QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = getattr(settings, "QDRANT_API_KEY", None)

        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self._client = None

    @property
    def client(self) -> QdrantClient:
        """Lazy initialization of Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
            self._ensure_collection()
            logger.info(f"ChatIndexManager initialized with collection '{self.COLLECTION_NAME}'")
        return self._client

    def _ensure_collection(self):
        """Create chat_metadata collection if it doesn't exist."""
        collections = self._client.get_collections().collections
        exists = any(col.name == self.COLLECTION_NAME for col in collections)

        if not exists:
            # Get dimension dynamically from embedder
            embedding_dimension = embedder.dimension
            logger.info(f"Creating Qdrant collection '{self.COLLECTION_NAME}' with dimension {embedding_dimension}")
            self._client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=embedding_dimension,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Collection '{self.COLLECTION_NAME}' created successfully")

    def _create_searchable_text(self, title: Optional[str], summary: Optional[str]) -> str:
        """
        Create searchable text from title and summary.

        Args:
            title: Chat title (optional)
            summary: Chat summary (optional)

        Returns:
            Combined text for embedding, or empty string if both are None
        """
        parts = []
        if title and title.strip():
            parts.append(title.strip())
        if summary and summary.strip():
            parts.append(summary.strip())

        return " | ".join(parts) if parts else ""

    async def index_chat(
        self,
        chat_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Index or update a chat in Qdrant.

        Args:
            chat_id: Unique chat identifier
            user_id: User ID (CRITICAL for security filtering)
            title: Chat title
            summary: Chat summary
            created_at: Chat creation timestamp

        Returns:
            Point ID if indexed, None if no searchable content
        """
        searchable_text = self._create_searchable_text(title, summary)

        # Skip indexing if no searchable content
        if not searchable_text:
            logger.debug(f"Skipping indexing for chat {chat_id}: no title or summary")
            return None

        try:
            # Generate embedding
            embedding = embedder.embed(searchable_text)

            # Use chat_id as point_id for easier updates/deletes
            point_id = str(chat_id)

            # Prepare payload with MANDATORY user_id for security
            payload = {
                "chat_id": str(chat_id),
                "user_id": str(user_id),  # ⚠️ CRITICAL: prevents cross-user access
                "title": title or "",
                "summary": summary or "",
                "created_at": created_at.isoformat() if created_at else datetime.utcnow().isoformat(),
                "searchable_text": searchable_text
            }

            # Upsert to Qdrant (insert or update)
            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )

            logger.debug(f"Indexed chat {chat_id} for user {user_id}")
            return point_id

        except Exception as e:
            logger.error(f"Failed to index chat {chat_id}: {e}", exc_info=True)
            raise

    async def search_chats(
        self,
        query: str,
        user_id: UUID,
        limit: int = 10,
        score_threshold: float = 0.3
    ) -> list[dict]:
        """
        Search chats using semantic similarity with MANDATORY user_id filtering.

        Args:
            query: Search query text
            user_id: User ID (CRITICAL: only returns this user's chats)
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of matching chats with scores, sorted by relevance
        """
        if not query or not query.strip():
            logger.warning("Empty query provided to search_chats")
            return []

        try:
            # Generate query embedding
            query_embedding = embedder.embed(query.strip())

            # Build filter with MANDATORY user_id isolation
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=str(user_id))
                    )
                ]
            )

            # Search in Qdrant
            query_response = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                limit=limit,
                query_filter=search_filter,
                score_threshold=score_threshold
            )

            # Format results
            formatted_results = []
            for result in query_response.points:
                formatted_results.append({
                    "chat_id": result.payload.get("chat_id"),
                    "user_id": result.payload.get("user_id"),
                    "title": result.payload.get("title"),
                    "summary": result.payload.get("summary"),
                    "created_at": result.payload.get("created_at"),
                    "score": float(result.score),
                    "searchable_text": result.payload.get("searchable_text")
                })

            logger.debug(f"Found {len(formatted_results)} chats for query '{query[:50]}...' (user {user_id})")
            return formatted_results

        except Exception as e:
            logger.error(f"Search failed for user {user_id}: {e}", exc_info=True)
            raise

    async def delete_chat(self, chat_id: UUID) -> bool:
        """
        Delete a chat from the index.

        Args:
            chat_id: Chat ID to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=[str(chat_id)]
            )
            logger.debug(f"Deleted chat {chat_id} from index")
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat {chat_id}: {e}", exc_info=True)
            return False

    async def delete_user_chats(self, user_id: UUID) -> int:
        """
        Delete all chats for a specific user (for GDPR compliance).

        Args:
            user_id: User ID

        Returns:
            Number of chats deleted
        """
        try:
            # Delete using filter
            result = self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=str(user_id))
                        )
                    ]
                )
            )
            logger.info(f"Deleted all chats for user {user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to delete chats for user {user_id}: {e}", exc_info=True)
            raise


# Factory function for singleton pattern
_chat_index_manager_instance = None


def get_chat_index_manager() -> ChatIndexManager:
    """
    Get or create ChatIndexManager singleton instance.

    Uses lazy initialization - Qdrant connection is established only on first use.
    """
    global _chat_index_manager_instance
    if _chat_index_manager_instance is None:
        _chat_index_manager_instance = ChatIndexManager()
    return _chat_index_manager_instance
