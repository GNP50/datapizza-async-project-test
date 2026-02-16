"""
In-memory cache for tracking currently processing messages.

This module provides a thread-safe cache to track which messages are actively
being processed by THIS worker instance. This prevents duplicate processing
while avoiding stale state issues that can occur with database-only checks.

Key benefits:
- Prevents duplicate task execution within the same worker
- Automatically clears on worker restart (no stale state)
- Thread-safe for concurrent task execution
- Complements (doesn't replace) database state tracking
"""

import threading
from typing import Set
import logging

logger = logging.getLogger(__name__)


class ProcessingCache:
    """Thread-safe in-memory cache for tracking active message processing."""

    def __init__(self):
        self._processing_messages: Set[str] = set()
        self._lock = threading.Lock()

    def add(self, message_id: str) -> bool:
        """
        Mark a message as being processed.

        Args:
            message_id: The message ID to track

        Returns:
            True if message was added (not already processing)
            False if message is already being processed
        """
        with self._lock:
            if message_id in self._processing_messages:
                logger.warning(
                    f"Message {message_id} is already being processed by this worker. "
                    f"Skipping duplicate task."
                )
                return False

            self._processing_messages.add(message_id)
            logger.debug(f"Added message {message_id} to processing cache")
            return True

    def remove(self, message_id: str) -> None:
        """
        Remove a message from the processing cache.

        Args:
            message_id: The message ID to remove
        """
        with self._lock:
            self._processing_messages.discard(message_id)
            logger.debug(f"Removed message {message_id} from processing cache")

    def is_processing(self, message_id: str) -> bool:
        """
        Check if a message is currently being processed.

        Args:
            message_id: The message ID to check

        Returns:
            True if the message is currently being processed
        """
        with self._lock:
            return message_id in self._processing_messages

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            count = len(self._processing_messages)
            self._processing_messages.clear()
            logger.info(f"Cleared processing cache ({count} entries)")

    def get_count(self) -> int:
        """Get the number of messages currently being processed."""
        with self._lock:
            return len(self._processing_messages)


# Global singleton instance
_processing_cache = ProcessingCache()


def get_processing_cache() -> ProcessingCache:
    """Get the global processing cache instance."""
    return _processing_cache


def clear_processing_cache() -> None:
    """Clear the global processing cache. Called on worker startup."""
    _processing_cache.clear()
