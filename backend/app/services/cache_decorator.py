"""
Cache decorator for automatically caching function responses in Redis.

Usage:
    from app.services.cache_decorator import cache_response

    @cache_response(prefix="chat", ttl=300)
    async def get_chat(chat_id: UUID, ...) -> ChatResponse:
        ...

Key format
----------
    cache:{prefix}:{primary_id}:{hash_of_remaining_args}

The *primary_id* is the value of the **first** safe argument (UUID/str/int/…).
Embedding it in the key (not just in the hash) allows targeted invalidation:

    await cache_manager.clear_pattern(f"cache:chat:{chat_id}:*")

Non-serialisable arguments (AsyncSession, Request, …) are silently skipped.
"""
import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable
from uuid import UUID

# Imported at module level so tests can patch it via
# `patch("app.services.cache_decorator.cache_manager", ...)`.
# The actual object is resolved after the module is imported, which avoids the
# circular-import issue because cache.py does not import cache_decorator.
from app.services.cache import cache_manager  # noqa: E402  (import after stdlib)

logger = logging.getLogger(__name__)

# Types whose string representation is stable and safe to use in cache keys
_SAFE_KEY_TYPES = (str, int, float, bool, UUID)


def _build_cache_key(prefix: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """
    Derive a deterministic cache key from the function arguments.

    Key format:  ``cache:{prefix}:{primary_id}:{hash_of_rest}``

    * *primary_id* – the value of the **first** safe argument found (UUID, str,
      int, float, bool).  Embedding it literally enables precise pattern-based
      invalidation without touching unrelated entries.
    * *hash_of_rest* – a short SHA-256 of the remaining safe arguments, so that
      different secondary parameters (e.g. ``current_user``) still produce
      distinct keys for the same entity.

    Non-serialisable arguments (AsyncSession, UploadFile, …) are silently
    ignored so the decorator works transparently on FastAPI endpoint functions.
    """
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    safe_args: list[tuple[str, Any]] = [
        (name, value)
        for name, value in bound.arguments.items()
        if isinstance(value, _SAFE_KEY_TYPES)
    ]

    # First safe arg becomes the human-readable primary ID in the key.
    if safe_args:
        primary_id = str(safe_args[0][1])
        rest_parts = [f"{n}={v}" for n, v in safe_args[1:]]
    else:
        primary_id = "no-id"
        rest_parts = []

    rest_hash = hashlib.sha256(":".join(rest_parts).encode()).hexdigest()[:16]
    return f"cache:{prefix}:{primary_id}:{rest_hash}"


def cache_response(prefix: str = "default", ttl: int | None = None) -> Callable:
    """
    Decorator that caches the return value of an *async* function in Redis.

    Args:
        prefix: Logical namespace for the cache key (e.g. "chat", "document").
        ttl:    Time-to-live in seconds.  Falls back to CacheManager.default_ttl
                when not specified.

    The decorated function must be async.  The first cache hit returns the
    deserialised value; on a miss the real function is called and the result is
    stored before being returned.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Uses the module-level cache_manager; tests can patch it with:
            #   patch("app.services.cache_decorator.cache_manager", mock)
            import app.services.cache_decorator as _self
            _cm = _self.cache_manager

            cache_key = _build_cache_key(prefix, func, args, kwargs)

            # --- cache hit ---
            try:
                cached = await _cm.get(cache_key)
                if cached is not None:
                    logger.debug("Cache HIT: %s", cache_key)
                    return cached
            except Exception as exc:
                logger.warning("Cache GET failed for %s: %s", cache_key, exc)

            # --- cache miss: call the real function ---
            result = await func(*args, **kwargs)

            # --- store result ---
            try:
                effective_ttl = ttl if ttl is not None else _cm.default_ttl
                serialisable = _to_serialisable(result)
                await _cm.set(cache_key, serialisable, ttl=effective_ttl)
                logger.debug("Cache SET: %s (ttl=%s)", cache_key, effective_ttl)
            except Exception as exc:
                # Never let cache errors break the response
                logger.warning("Cache SET failed for %s: %s", cache_key, exc)

            return result

        # Attach metadata so callers can build/delete keys programmatically
        wrapper._cache_prefix = prefix  # type: ignore[attr-defined]
        wrapper._cache_func = func      # type: ignore[attr-defined]
        return wrapper

    return decorator


def _to_serialisable(value: Any) -> Any:
    """
    Convert a value to something JSON-serialisable.

    Pydantic models are converted via `.model_dump()`.
    Lists/dicts are processed recursively.
    Everything else is converted to its string representation as a last resort.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, UUID):
        return str(value)
    # Pydantic v2
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    # Pydantic v1 compat
    if hasattr(value, "dict"):
        try:
            return json.loads(value.json())
        except Exception:
            return value.dict()
    if isinstance(value, list):
        return [_to_serialisable(item) for item in value]
    if isinstance(value, dict):
        return {k: _to_serialisable(v) for k, v in value.items()}
    # Fallback: try JSON round-trip, otherwise str
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def build_cache_key_for(func: Callable, prefix: str, **kwargs: Any) -> str:
    """
    Helper to build the same cache key that the decorator would produce,
    useful for manual cache invalidation.

    Example:
        key = build_cache_key_for(get_chat, prefix="chat", chat_id=chat_id)
        await cache_manager.delete(key)
    """
    return _build_cache_key(prefix, func, args=(), kwargs=kwargs)
