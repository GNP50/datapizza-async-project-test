from abc import ABC, abstractmethod
from sentence_transformers import SentenceTransformer
from app.core.config import get_settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        pass


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self._dimension = self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        embedding = self.model.encode(text)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts)
        return embeddings.tolist()

    def get_dimension(self) -> int:
        return self._dimension


class EmbeddingManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        settings = get_settings()
        embedding_model = getattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.provider = SentenceTransformerProvider(model_name=embedding_model)
        self._initialized = True

    def embed(self, text: str) -> list[float]:
        return self.provider.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_batch(texts)

    def get_dimension(self) -> int:
        return self.provider.get_dimension()


embedding_manager = EmbeddingManager()
