from app.services.rag.embedder import embedder
from .qdrant import get_qdrant_manager
from .chat_index import get_chat_index_manager

__all__ = [
    "embedder",
    "qdrant_manager",
    "chat_index_manager",
    "get_qdrant_manager",
    "get_chat_index_manager",
]


def __getattr__(name):
    """
    Lazy loading of manager instances for backward compatibility.

    This allows imports like 'from app.services.vector import chat_index_manager'
    without triggering immediate initialization.
    """
    if name == "qdrant_manager":
        return get_qdrant_manager()
    elif name == "chat_index_manager":
        return get_chat_index_manager()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
