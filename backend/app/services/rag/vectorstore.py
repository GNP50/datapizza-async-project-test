from urllib.parse import urlparse
from typing import Optional
from uuid import UUID
from datapizza.vectorstores.qdrant import QdrantVectorstore
from datapizza.type import Chunk
from app.core.config import get_settings
from .embedder import embedder
import logging

logger = logging.getLogger(__name__)


class VectorstoreWrapper:
    """Wrapper around QdrantVectorstore that provides a simplified interface with chat-level isolation."""

    def __init__(self, qdrant_store: QdrantVectorstore, default_collection: str = "documents"):
        self.store = qdrant_store
        self.default_collection = default_collection
        self._initialized = False

    def _ensure_async_client(self):
        """
        Ensure the async client is valid for the current event loop.
        This prevents 'Event loop is closed' errors when using asyncio.run() in Celery tasks.

        When Celery tasks use asyncio.run(), a new event loop is created for each task,
        then closed when the task completes. If the AsyncQdrantClient persists across
        task invocations, it will try to use the closed event loop, causing
        "Event loop is closed" errors. This method forces recreation of the client
        for each new event loop.
        """
        import asyncio

        # If the async client exists, delete it to force recreation with current loop
        if hasattr(self.store, 'a_client'):
            try:
                # Try to get the current event loop
                asyncio.get_running_loop()
                # If we got here, we're in an async context
                # Delete the old client so it gets recreated with the current loop
                logger.debug("Resetting async Qdrant client for current event loop")
                delattr(self.store, 'a_client')
            except RuntimeError:
                # No running loop - this shouldn't happen since we're in an async method,
                # but if it does, delete the client anyway to be safe
                logger.warning("No running event loop detected, but resetting client anyway")
                delattr(self.store, 'a_client')

    def initialize(self):
        """
        Initialize the vectorstore by ensuring the default collection exists.
        This should be called during application startup.
        """
        if self._initialized:
            logger.debug(f"Vectorstore already initialized")
            return

        from datapizza.type import EmbeddingFormat
        from datapizza.core.vectorstore import VectorConfig

        try:
            client = self.store.get_client()
            # Check if collection exists
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.default_collection not in collection_names:
                # Detect dimension from the active embedder
                dim = embedder.dimension
                logger.info(f"Creating collection '{self.default_collection}' with dimension={dim}")
                self.store.create_collection(
                    collection_name=self.default_collection,
                    vector_config=[
                        VectorConfig(
                            name="default",
                            format=EmbeddingFormat.DENSE,
                            dimensions=dim,
                        )
                    ]
                )
                logger.info(f"Successfully created collection '{self.default_collection}'")
            else:
                logger.debug(f"Collection '{self.default_collection}' already exists")

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize vectorstore collection '{self.default_collection}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize vectorstore collection: {e}") from e

    async def a_add(
        self,
        chunks: Chunk | list[Chunk],
        chat_id: UUID,
        collection_name: Optional[str] = None
    ):
        """
        Add chunks to the vectorstore with chat_id isolation.

        Args:
            chunks: Chunk or list of chunks to add
            chat_id: Chat ID for isolation - ensures vectors are only accessible within this chat
            collection_name: Optional collection name override
        """
        collection = collection_name or self.default_collection

        # Ensure all chunks have chat_id in metadata for isolation
        chunks_list = [chunks] if isinstance(chunks, Chunk) else chunks

        logger.debug(f"Adding {len(chunks_list)} chunks to collection '{collection}' for chat {chat_id}")

        for chunk in chunks_list:
            chunk.metadata["chat_id"] = str(chat_id)

        try:
            # Reset async client to ensure it uses the current event loop
            self._ensure_async_client()
            await self.store.a_add(chunks_list, collection_name=collection)
            logger.debug(f"Successfully added {len(chunks_list)} chunks to vectorstore")
        except Exception as e:
            logger.error(f"Failed to add chunks to vectorstore: {e}", exc_info=True)
            raise

    async def a_search(
        self,
        query: str,
        chat_id: UUID,
        top_k: int = 10,
        filter: Optional[dict] = None,
        collection_name: Optional[str] = None
    ) -> list[Chunk]:
        """
        Search the vectorstore using a text query with chat_id isolation.

        Args:
            query: Text query to search for
            chat_id: Chat ID for isolation - only returns vectors from this chat
            top_k: Number of results to return
            filter: Optional additional filters
            collection_name: Optional collection name override

        Returns:
            List of chunks matching the query within the specified chat
        """
        collection = collection_name or self.default_collection

        # Generate embedding for the query
        query_embedding = await embedder.a_embed([query])
        query_vector = query_embedding[0]

        # Build filter with MANDATORY chat_id isolation
        from qdrant_client import models
        must_conditions = [
            # CRITICAL: Always filter by chat_id to prevent cross-chat data leakage
            models.FieldCondition(
                key="chat_id",
                match=models.MatchValue(value=str(chat_id))
            )
        ]

        # Add any additional filters
        if filter:
            for key, value in filter.items():
                # Don't allow overriding chat_id filter
                if key != "chat_id":
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value)
                        )
                    )

        kwargs = {"query_filter": models.Filter(must=must_conditions)}

        # Reset async client to ensure it uses the current event loop
        self._ensure_async_client()

        # Query Qdrant directly to get scored results (datapizza discards scores)
        # Using query_points (qdrant-client >= 1.12 removed .search())
        a_client = self.store._get_a_client()
        query_response = await a_client.query_points(
            collection_name=collection,
            query=query_vector,
            using="default",
            limit=top_k,
            **kwargs
        )

        # Convert scored points to Chunk objects preserving scores
        from datapizza.type import DenseEmbedding
        results = []
        for sp in query_response.points:
            payload = sp.payload or {}
            chunk = Chunk(
                id=str(sp.id),
                metadata=payload,
                text=payload.get("text", ""),
                embeddings=[],
            )
            chunk.score = sp.score
            results.append(chunk)

        return results

    async def a_delete_by_document(
        self,
        document_id: UUID,
        collection_name: Optional[str] = None
    ) -> int:
        """
        Delete all vectors associated with a specific document.

        Args:
            document_id: Document ID to delete vectors for
            collection_name: Optional collection name override

        Returns:
            Number of vectors deleted
        """
        collection = collection_name or self.default_collection

        # Reset async client to ensure it uses the current event loop
        self._ensure_async_client()

        # Build filter to delete all vectors for this document
        from qdrant_client import models

        try:
            a_client = self.store._get_a_client()

            # Delete points matching document_id
            result = await a_client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=str(document_id))
                            )
                        ]
                    )
                )
            )

            logger.info(f"Deleted vectors for document {document_id} from collection '{collection}'")
            return 1  # Qdrant doesn't return count, so return 1 if successful

        except Exception as e:
            logger.error(f"Failed to delete vectors for document {document_id}: {e}", exc_info=True)
            raise


def get_vectorstore() -> VectorstoreWrapper:
    settings = get_settings()
    qdrant_url = settings.qdrant_url

    # Parse the URL to extract host and port
    parsed = urlparse(qdrant_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333

    qdrant_store = QdrantVectorstore(
        host=host,
        port=port,
        api_key=settings.qdrant_api_key
    )

    return VectorstoreWrapper(qdrant_store)


vectorstore = get_vectorstore()
