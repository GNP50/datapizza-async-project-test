"""
Tests for:
  - CacheManager (Redis L1 wrapper)
  - @cache_response decorator
  - Cache invalidation via clear_pattern
  - TTL configuration
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import UUID, uuid4

import app.services.cache_decorator as cache_decorator_module
from app.services.cache import CacheManager
from app.services.cache_decorator import (
    _build_cache_key,
    _to_serialisable,
    cache_response,
    build_cache_key_for,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_cache_manager(default_ttl: int = 300) -> CacheManager:
    """Return a CacheManager whose Redis client is replaced with an AsyncMock."""
    mgr = CacheManager.__new__(CacheManager)
    mgr.settings = MagicMock()
    mgr.settings.cache_ttl = default_ttl
    mgr.default_ttl = default_ttl
    mgr.redis = AsyncMock()
    return mgr


# ---------------------------------------------------------------------------
# CacheManager unit tests
# ---------------------------------------------------------------------------

class TestCacheManager:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_redis_is_none(self):
        mgr = CacheManager.__new__(CacheManager)
        mgr.settings = MagicMock()
        mgr.settings.cache_ttl = 3600
        mgr.default_ttl = 3600
        mgr.redis = None

        result = await mgr.get("any-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_deserialises_json(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(return_value=json.dumps({"hello": "world"}))

        result = await mgr.get("k")
        assert result == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_get_returns_raw_string_on_json_error(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(return_value="not-json")

        result = await mgr.get("k")
        assert result == "not-json"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_key_missing(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(return_value=None)

        result = await mgr.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_uses_default_ttl_when_none_given(self):
        mgr = make_cache_manager(default_ttl=42)
        mgr.redis.setex = AsyncMock(return_value=True)

        await mgr.set("k", {"a": 1})

        mgr.redis.setex.assert_awaited_once_with("k", 42, json.dumps({"a": 1}))

    @pytest.mark.asyncio
    async def test_set_uses_explicit_ttl(self):
        mgr = make_cache_manager(default_ttl=3600)
        mgr.redis.setex = AsyncMock(return_value=True)

        await mgr.set("k", "value", ttl=10)

        mgr.redis.setex.assert_awaited_once_with("k", 10, "value")

    @pytest.mark.asyncio
    async def test_set_returns_false_when_redis_none(self):
        mgr = CacheManager.__new__(CacheManager)
        mgr.settings = MagicMock()
        mgr.settings.cache_ttl = 3600
        mgr.default_ttl = 3600
        mgr.redis = None

        result = await mgr.set("k", "v")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        mgr = make_cache_manager()
        mgr.redis.delete = AsyncMock(return_value=1)

        result = await mgr.delete("k")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_key_absent(self):
        mgr = make_cache_manager()
        mgr.redis.delete = AsyncMock(return_value=0)

        result = await mgr.delete("k")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self):
        mgr = make_cache_manager()
        mgr.redis.exists = AsyncMock(return_value=1)

        assert await mgr.exists("k") is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        mgr = make_cache_manager()
        mgr.redis.exists = AsyncMock(return_value=0)

        assert await mgr.exists("k") is False

    @pytest.mark.asyncio
    async def test_clear_pattern_deletes_matched_keys(self):
        mgr = make_cache_manager()
        mgr.redis.keys = AsyncMock(return_value=["k1", "k2"])
        mgr.redis.delete = AsyncMock(return_value=2)

        count = await mgr.clear_pattern("k*")
        assert count == 2
        mgr.redis.delete.assert_awaited_once_with("k1", "k2")

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_when_no_keys(self):
        mgr = make_cache_manager()
        mgr.redis.keys = AsyncMock(return_value=[])

        count = await mgr.clear_pattern("nothing*")
        assert count == 0

    def test_default_ttl_comes_from_settings(self):
        with patch("app.services.cache.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                redis_url="redis://localhost:6379/0",
                cache_ttl=123
            )
            mgr = CacheManager()
        assert mgr.default_ttl == 123


# ---------------------------------------------------------------------------
# cache_decorator helpers
# ---------------------------------------------------------------------------

class TestBuildCacheKey:
    def test_same_args_produce_same_key(self):
        async def my_func(chat_id: UUID, current_user=None, db=None):
            pass

        uid = uuid4()
        k1 = _build_cache_key("chat", my_func, (uid,), {"current_user": object(), "db": object()})
        k2 = _build_cache_key("chat", my_func, (uid,), {"current_user": object(), "db": object()})
        assert k1 == k2

    def test_different_args_produce_different_keys(self):
        async def my_func(chat_id: UUID):
            pass

        k1 = _build_cache_key("chat", my_func, (uuid4(),), {})
        k2 = _build_cache_key("chat", my_func, (uuid4(),), {})
        assert k1 != k2

    def test_key_contains_prefix_and_primary_id(self):
        async def get_thing(thing_id: str):
            pass

        key = _build_cache_key("things", get_thing, ("abc",), {})
        # Key format: cache:{prefix}:{primary_id}:{rest_hash}
        assert key.startswith("cache:things:abc:")

    def test_non_safe_args_are_ignored(self):
        """DB sessions and other objects must NOT affect the key."""
        async def my_func(chat_id: str, db=None):
            pass

        sentinel = object()
        k1 = _build_cache_key("x", my_func, ("same",), {"db": sentinel})
        k2 = _build_cache_key("x", my_func, ("same",), {"db": object()})
        assert k1 == k2


class TestToSerialisable:
    def test_primitive_passthrough(self):
        assert _to_serialisable(42) == 42
        assert _to_serialisable("hello") == "hello"
        assert _to_serialisable(True) is True
        assert _to_serialisable(None) is None

    def test_uuid_becomes_string(self):
        uid = uuid4()
        result = _to_serialisable(uid)
        assert result == str(uid)

    def test_list_is_processed_recursively(self):
        uid = uuid4()
        result = _to_serialisable([uid, 1, "x"])
        assert result == [str(uid), 1, "x"]

    def test_dict_is_processed_recursively(self):
        uid = uuid4()
        result = _to_serialisable({"id": uid, "count": 3})
        assert result == {"id": str(uid), "count": 3}

    def test_pydantic_v2_model(self):
        from pydantic import BaseModel

        class Foo(BaseModel):
            x: int
            y: str

        foo = Foo(x=1, y="hello")
        result = _to_serialisable(foo)
        assert result == {"x": 1, "y": "hello"}

    def test_unknown_non_serialisable_falls_back_to_str(self):
        class Blob:
            def __str__(self):
                return "blob-repr"

        result = _to_serialisable(Blob())
        assert result == "blob-repr"


# ---------------------------------------------------------------------------
# @cache_response decorator
# ---------------------------------------------------------------------------

class TestCacheResponseDecorator:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_function_and_stores_result(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(return_value=None)
        mgr.redis.setex = AsyncMock(return_value=True)

        call_count = 0

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="test", ttl=60)
            async def my_func(x: int) -> dict:
                nonlocal call_count
                call_count += 1
                return {"value": x}

            result = await my_func(x=5)

        assert result == {"value": 5}
        assert call_count == 1
        mgr.redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_function(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(return_value=json.dumps({"value": 99}))

        call_count = 0

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="test")
            async def my_func(x: int) -> dict:
                nonlocal call_count
                call_count += 1
                return {"value": x}

            result = await my_func(x=5)

        assert result == {"value": 99}
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_different_inputs_have_different_keys(self):
        stored: dict[str, str] = {}

        mgr = make_cache_manager()

        async def fake_get(key: str):
            return stored.get(key)

        async def fake_setex(key: str, ttl: int, val: str):
            stored[key] = val
            return True

        mgr.redis.get = fake_get
        mgr.redis.setex = fake_setex

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="fn")
            async def compute(n: int) -> int:
                return n * 2

            r1 = await compute(n=3)
            r2 = await compute(n=7)

        assert r1 == 6
        assert r2 == 14
        # Two distinct keys must have been stored
        assert len(stored) == 2

    @pytest.mark.asyncio
    async def test_second_call_uses_cache(self):
        """Calling with the same args twice should only invoke the real function once."""
        # Simulate the full round-trip: setex stores a JSON-encoded string,
        # get returns that string, and CacheManager.get() does json.loads on it.
        stored: dict[str, str] = {}

        mgr = make_cache_manager()

        async def fake_redis_get(key: str):
            """Returns the raw stored string (as the real Redis would)."""
            return stored.get(key)

        async def fake_setex(key: str, ttl: int, val: str):
            stored[key] = val
            return True

        mgr.redis.get = fake_redis_get
        mgr.redis.setex = fake_setex

        call_count = 0

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="fn")
            async def expensive(n: int) -> int:
                nonlocal call_count
                call_count += 1
                return n + 1

            r1 = await expensive(n=10)
            r2 = await expensive(n=10)

        assert r1 == 11
        assert r2 == 11
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cache_error_does_not_break_function(self):
        mgr = make_cache_manager()
        mgr.redis.get = AsyncMock(side_effect=Exception("Redis down"))
        mgr.redis.setex = AsyncMock(side_effect=Exception("Redis down"))

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="test")
            async def safe_func(x: int) -> int:
                return x * 3

            result = await safe_func(x=4)

        assert result == 12  # Function still works despite Redis failure

    @pytest.mark.asyncio
    async def test_custom_ttl_is_used(self):
        mgr = make_cache_manager(default_ttl=9999)
        mgr.redis.get = AsyncMock(return_value=None)
        mgr.redis.setex = AsyncMock(return_value=True)

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="ttl_test", ttl=77)
            async def fn(x: int) -> int:
                return x

            await fn(x=1)

        # First positional arg to setex is key, second is TTL
        _, ttl_arg, _ = mgr.redis.setex.call_args.args
        assert ttl_arg == 77

    @pytest.mark.asyncio
    async def test_default_ttl_used_when_not_specified(self):
        mgr = make_cache_manager(default_ttl=42)
        mgr.redis.get = AsyncMock(return_value=None)
        mgr.redis.setex = AsyncMock(return_value=True)

        with patch.object(cache_decorator_module, "cache_manager", mgr):
            @cache_response(prefix="ttl_test")
            async def fn(x: int) -> int:
                return x

            await fn(x=1)

        _, ttl_arg, _ = mgr.redis.setex.call_args.args
        assert ttl_arg == 42

    def test_decorator_preserves_function_name(self):
        @cache_response(prefix="meta")
        async def my_named_function(x: int) -> int:
            return x

        assert my_named_function.__name__ == "my_named_function"

    def test_decorator_exposes_prefix_attribute(self):
        @cache_response(prefix="exposed")
        async def fn(x: int) -> int:
            return x

        assert fn._cache_prefix == "exposed"


# ---------------------------------------------------------------------------
# build_cache_key_for helper
# ---------------------------------------------------------------------------

class TestBuildCacheKeyFor:
    def test_returns_expected_pattern(self):
        async def get_doc(document_id: UUID, current_user=None, db=None):
            pass

        uid = uuid4()
        key = build_cache_key_for(get_doc, prefix="document", document_id=uid)
        # Key format: cache:{prefix}:{primary_id}:{rest_hash}
        assert key.startswith(f"cache:document:{uid}:")

    def test_consistent_with_decorator_key(self):
        """Key from helper must match what the decorator builds for the same inputs."""
        async def get_item(item_id: str, db=None):
            pass

        key_helper = build_cache_key_for(get_item, prefix="item", item_id="abc")
        key_decorator = _build_cache_key("item", get_item, args=(), kwargs={"item_id": "abc", "db": None})
        assert key_helper == key_decorator


# ---------------------------------------------------------------------------
# Cache invalidation (pattern-based) unit tests
# ---------------------------------------------------------------------------

class TestCachePatternInvalidation:
    @pytest.mark.asyncio
    async def test_clear_specific_document_key_only(self):
        """
        Invalidating cache:document:{doc_id}:* must only remove keys for that
        specific document and leave all other entries untouched.
        """
        doc_id_a = uuid4()
        doc_id_b = uuid4()
        chat_id  = uuid4()

        stored = {
            f"cache:document:{doc_id_a}:aaa": "v1",
            f"cache:document:{doc_id_b}:bbb": "v2",
            f"cache:chat:{chat_id}:ccc":       "v3",
        }

        mgr = make_cache_manager()

        async def fake_keys(pattern: str):
            import fnmatch
            return [k for k in stored if fnmatch.fnmatch(k, pattern)]

        async def fake_delete(*keys):
            for k in keys:
                stored.pop(k, None)
            return len(keys)

        mgr.redis.keys = fake_keys
        mgr.redis.delete = fake_delete

        # Invalidate only doc_id_a
        deleted = await mgr.clear_pattern(f"cache:document:{doc_id_a}:*")

        assert deleted == 1
        assert f"cache:document:{doc_id_a}:aaa" not in stored   # removed
        assert f"cache:document:{doc_id_b}:bbb" in stored        # untouched
        assert f"cache:chat:{chat_id}:ccc" in stored             # untouched

    @pytest.mark.asyncio
    async def test_clear_specific_chat_key_does_not_affect_others(self):
        """
        Invalidating cache:chat:{chat_id}:* must leave other chats and
        document entries intact.
        """
        chat_id_x = uuid4()
        chat_id_y = uuid4()
        doc_id    = uuid4()

        stored = {
            f"cache:chat:{chat_id_x}:111": "c1",
            f"cache:chat:{chat_id_y}:222": "c2",
            f"cache:document:{doc_id}:333": "d1",
        }

        mgr = make_cache_manager()

        async def fake_keys(pattern: str):
            import fnmatch
            return [k for k in stored if fnmatch.fnmatch(k, pattern)]

        async def fake_delete(*keys):
            for k in keys:
                stored.pop(k, None)
            return len(keys)

        mgr.redis.keys = fake_keys
        mgr.redis.delete = fake_delete

        await mgr.clear_pattern(f"cache:chat:{chat_id_x}:*")

        assert f"cache:chat:{chat_id_x}:111" not in stored   # removed
        assert f"cache:chat:{chat_id_y}:222" in stored        # untouched
        assert f"cache:document:{doc_id}:333" in stored       # untouched
