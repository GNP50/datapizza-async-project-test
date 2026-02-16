"""
Embedding factory — creates the right embedder based on configuration.

Supports:
  - ollama:      uses the official ollama Python library (local or api.ollama.com)
  - openai:      uses datapizza's OpenAIEmbedder (text-embedding-3-small, etc.)
  - openai_like: uses datapizza's OpenAIEmbedder with a custom base_url
  - auto:        follows llm_provider, or auto-detects from env vars (default)
"""
import logging
import ollama
from datapizza.core.embedder import BaseEmbedder
from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ollama embedder (uses official ollama library)
# ---------------------------------------------------------------------------
class OllamaEmbedder(BaseEmbedder):
    """Embedder using the official ollama Python library."""

    def __init__(self, base_url: str, api_key: str | None, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._dimension: int | None = None

        # Only pass headers if API key exists
        if api_key:
            headers = {"Authorization": f"Bearer {api_key}"}
            self._sync_client = ollama.Client(host=base_url, headers=headers)
        else:
            self._sync_client = ollama.Client(host=base_url)

    def _get_async_client(self) -> ollama.AsyncClient:
        """Fresh async client each call (avoids event-loop issues in Celery)."""
        # Only pass headers if API key exists
        if self.api_key:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            return ollama.AsyncClient(host=self.base_url, headers=headers)
        else:
            return ollama.AsyncClient(host=self.base_url)

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            vec = self.embed("test")
            self._dimension = len(vec)
        return self._dimension

    def embed(self, text: str) -> list[float]:
        try:
            resp = self._sync_client.embed(model=self.model, input=text)
            embeddings = resp.get("embeddings", [])
            if embeddings:
                self._dimension = len(embeddings[0])
                return embeddings[0]
            logger.warning("Ollama embed returned empty result")
            return [0.0] * (self._dimension or 768)
        except Exception as e:
            logger.error(f"Ollama embed failed: {e}")
            return [0.0] * (self._dimension or 768)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self._sync_client.embed(model=self.model, input=texts)
            embeddings = resp.get("embeddings", [])
            if embeddings:
                self._dimension = len(embeddings[0])
                return embeddings
            logger.warning("Ollama batch embed returned empty result")
            return [[0.0] * (self._dimension or 768) for _ in texts]
        except Exception as e:
            logger.error(f"Ollama batch embed failed: {e}")
            return [[0.0] * (self._dimension or 768) for _ in texts]

    async def a_embed(self, texts: list[str]) -> list[list[float]]:
        try:
            a_client = self._get_async_client()
            resp = await a_client.embed(model=self.model, input=texts)
            embeddings = resp.get("embeddings", [])
            if embeddings:
                self._dimension = len(embeddings[0])
                return embeddings
            logger.warning("Ollama async embed returned empty result")
            return [[0.0] * (self._dimension or 768) for _ in texts]
        except Exception as e:
            logger.error(f"Ollama async embed failed: {e}")
            return [[0.0] * (self._dimension or 768) for _ in texts]


# ---------------------------------------------------------------------------
# OpenAI-compatible embedder (wraps datapizza OpenAIEmbedder)
# ---------------------------------------------------------------------------
class OpenAICompatEmbedder(BaseEmbedder):
    """
    Embedder backed by datapizza's OpenAIEmbedder.
    Works with OpenAI and any OpenAI-compatible API (via base_url).
    """

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        from datapizza.embedders.openai import OpenAIEmbedder as DPOpenAIEmbedder

        self.model = model
        self._dimension: int | None = None
        self._dp_embedder = DPOpenAIEmbedder(
            api_key=api_key,
            model_name=model,
            base_url=base_url,
        )
        logger.info(
            f"OpenAICompatEmbedder initialised: model={model}, "
            f"base_url={base_url or 'default'}"
        )

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            vec = self.embed("test")
            self._dimension = len(vec)
        return self._dimension

    # -- sync -----------------------------------------------------------------
    def embed(self, text: str) -> list[float]:
        try:
            result = self._dp_embedder.embed(text)
            if result:
                self._dimension = len(result)
            return result
        except Exception as e:
            logger.error(f"OpenAI embed failed: {e}")
            return [0.0] * (self._dimension or 1536)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            result = self._dp_embedder.embed(texts)
            if result and isinstance(result[0], list):
                self._dimension = len(result[0])
                return result
            if result:
                self._dimension = len(result)
                return [result]
            return [[0.0] * (self._dimension or 1536) for _ in texts]
        except Exception as e:
            logger.error(f"OpenAI batch embed failed: {e}")
            return [[0.0] * (self._dimension or 1536) for _ in texts]

    # -- async ----------------------------------------------------------------
    async def a_embed(self, texts: list[str]) -> list[list[float]]:
        try:
            result = await self._dp_embedder.a_embed(texts)
            if result and isinstance(result[0], list):
                self._dimension = len(result[0])
                return result
            if result:
                self._dimension = len(result)
                return [result]
            return [[0.0] * (self._dimension or 1536) for _ in texts]
        except Exception as e:
            logger.error(f"OpenAI async embed failed: {e}")
            return [[0.0] * (self._dimension or 1536) for _ in texts]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_embedder() -> BaseEmbedder:
    """
    Create the correct embedder based on configuration.

    Resolution order for provider:
      1. EMBEDDING_PROVIDER env var (explicit: "ollama", "openai", "openai_like")
      2. If "auto" (default):
         a. OPENAI_API_KEY + OPENAI_EMBEDDING_MODEL set → openai
         b. else → follows LLM_PROVIDER
    """
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    # -- auto-resolve ---------------------------------------------------------
    if provider == "auto":
        openai_emb_model = settings.openai_embedding_model
        openai_key = settings.openai_api_key
        if openai_emb_model and openai_key:
            provider = "openai"
            logger.info(
                "Embedding provider auto-resolved to 'openai' "
                "(OPENAI_EMBEDDING_MODEL is set)"
            )
        else:
            provider = settings.llm_provider.lower()
            logger.info(
                f"Embedding provider auto-resolved to '{provider}' "
                "(follows LLM_PROVIDER)"
            )

    # -- openai ---------------------------------------------------------------
    if provider == "openai":
        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when using openai embedding provider"
            )
        model = settings.openai_embedding_model or settings.embedding_model
        base_url = settings.openai_base_url  # None → default OpenAI URL
        logger.info(f"Creating OpenAI embedder: model={model}")
        return OpenAICompatEmbedder(api_key=api_key, model=model, base_url=base_url)

    # -- openai_like ----------------------------------------------------------
    if provider == "openai_like":
        api_key = settings.openai_api_key or settings.ollama_api_key or ""
        model = settings.openai_embedding_model or settings.embedding_model
        base_url = settings.openai_base_url or f"{settings.ollama_base_url}/v1"
        logger.info(f"Creating OpenAI-like embedder: model={model}, base_url={base_url}")
        return OpenAICompatEmbedder(api_key=api_key, model=model, base_url=base_url)

    # -- ollama (default) -----------------------------------------------------
    logger.info(
        f"Creating Ollama embedder: model={settings.embedding_model}, "
        f"url={settings.ollama_base_url}"
    )
    return OllamaEmbedder(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        model=settings.embedding_model,
    )


embedder = get_embedder()
