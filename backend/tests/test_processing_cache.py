"""
Tests for the in-memory processing cache.

Validates that the cache correctly tracks active message processing
and prevents duplicate task execution within a worker instance.
"""

import pytest
import threading
import time
from app.worker.utils.processing_cache import ProcessingCache


def test_processing_cache_basic():
    """Test basic add/remove/check operations."""
    cache = ProcessingCache()

    # Should successfully add first time
    assert cache.add("msg-1") is True
    assert cache.is_processing("msg-1") is True

    # Should fail to add duplicate
    assert cache.add("msg-1") is False
    assert cache.is_processing("msg-1") is True

    # Should remove successfully
    cache.remove("msg-1")
    assert cache.is_processing("msg-1") is False

    # Should be able to add again after removal
    assert cache.add("msg-1") is True
    assert cache.is_processing("msg-1") is True


def test_processing_cache_multiple_messages():
    """Test handling multiple messages simultaneously."""
    cache = ProcessingCache()

    # Add multiple messages
    assert cache.add("msg-1") is True
    assert cache.add("msg-2") is True
    assert cache.add("msg-3") is True

    # All should be tracked
    assert cache.is_processing("msg-1") is True
    assert cache.is_processing("msg-2") is True
    assert cache.is_processing("msg-3") is True
    assert cache.get_count() == 3

    # Remove one
    cache.remove("msg-2")
    assert cache.is_processing("msg-1") is True
    assert cache.is_processing("msg-2") is False
    assert cache.is_processing("msg-3") is True
    assert cache.get_count() == 2


def test_processing_cache_clear():
    """Test clearing all entries."""
    cache = ProcessingCache()

    # Add multiple messages
    cache.add("msg-1")
    cache.add("msg-2")
    cache.add("msg-3")
    assert cache.get_count() == 3

    # Clear all
    cache.clear()
    assert cache.get_count() == 0
    assert cache.is_processing("msg-1") is False
    assert cache.is_processing("msg-2") is False
    assert cache.is_processing("msg-3") is False


def test_processing_cache_thread_safety():
    """Test that cache operations are thread-safe."""
    cache = ProcessingCache()
    results = {"duplicates": 0, "success": 0}
    lock = threading.Lock()

    def try_add_message(message_id: str):
        """Try to add a message and track results."""
        if cache.add(message_id):
            with lock:
                results["success"] += 1
        else:
            with lock:
                results["duplicates"] += 1

    # Create 10 threads all trying to add the same message
    threads = []
    for i in range(10):
        thread = threading.Thread(target=try_add_message, args=("msg-concurrent",))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Only one should succeed, 9 should be duplicates
    assert results["success"] == 1
    assert results["duplicates"] == 9
    assert cache.is_processing("msg-concurrent") is True


def test_processing_cache_remove_nonexistent():
    """Test that removing a non-existent message doesn't raise errors."""
    cache = ProcessingCache()

    # Should not raise error
    cache.remove("msg-nonexistent")
    assert cache.is_processing("msg-nonexistent") is False


def test_processing_cache_worker_restart_simulation():
    """Simulate worker restart scenario."""
    # Create cache with some entries (simulating active processing)
    cache = ProcessingCache()
    cache.add("msg-1")
    cache.add("msg-2")
    assert cache.get_count() == 2

    # Simulate worker restart by clearing cache
    cache.clear()

    # After "restart", cache should be empty
    assert cache.get_count() == 0
    assert cache.is_processing("msg-1") is False
    assert cache.is_processing("msg-2") is False

    # Should be able to process same messages again
    assert cache.add("msg-1") is True
    assert cache.add("msg-2") is True
