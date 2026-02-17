from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from uuid import UUID, uuid4
from app.core.config import get_settings
from app.services.rag.embedder import embedder


class QdrantManager:
    def __init__(self):
        settings = get_settings()
        qdrant_url = getattr(settings, "QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = getattr(settings, "QDRANT_API_KEY", None)

        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self.collection_name = "documents"
        self._client = None

    @property
    def client(self) -> QdrantClient:
        """Lazy initialization of Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
            self._ensure_collection()
        return self._client

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        exists = any(col.name == self.collection_name for col in collections)

        if not exists:
            # Get dimension dynamically from embedder
            embedding_dimension = embedder.dimension
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_dimension,
                    distance=Distance.COSINE
                )
            )

    async def add_document(
        self, 
        document_id: UUID,
        text: str,
        metadata: dict | None = None
    ) -> str:
        embedding = embedder.embed(text)
        
        point_id = str(uuid4())
        payload = {
            "document_id": str(document_id),
            "text": text,
            **(metadata or {})
        }
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        
        return point_id

    async def add_documents_batch(
        self,
        documents: list[tuple[UUID, str, dict | None]]
    ) -> list[str]:
        texts = [doc[1] for doc in documents]
        embeddings = embedder.embed_batch(texts)
        
        points = []
        point_ids = []
        
        for (doc_id, text, metadata), embedding in zip(documents, embeddings):
            point_id = str(uuid4())
            point_ids.append(point_id)
            
            payload = {
                "document_id": str(doc_id),
                "text": text,
                **(metadata or {})
            }
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            ))
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        return point_ids

    async def search(
        self, 
        query: str, 
        limit: int = 5,
        filter_conditions: dict | None = None
    ) -> list[dict]:
        query_embedding = embedder.embed(query)
        
        query_response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="default",
            limit=limit,
            query_filter=filter_conditions
        )

        return [
            {
                "id": result.id,
                "score": result.score,
                "document_id": result.payload.get("document_id"),
                "text": result.payload.get("text"),
                "metadata": {k: v for k, v in result.payload.items()
                           if k not in ["document_id", "text"]}
            }
            for result in query_response.points
        ]

    async def delete_by_document_id(self, document_id: UUID):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector={
                "filter": {
                    "must": [
                        {
                            "key": "document_id",
                            "match": {"value": str(document_id)}
                        }
                    ]
                }
            }
        )


# Factory function for singleton pattern
_qdrant_manager_instance = None


def get_qdrant_manager() -> QdrantManager:
    """
    Get or create QdrantManager singleton instance.

    Uses lazy initialization - Qdrant connection is established only on first use.
    """
    global _qdrant_manager_instance
    if _qdrant_manager_instance is None:
        _qdrant_manager_instance = QdrantManager()
    return _qdrant_manager_instance
