"""
Processing Cache Service - Manages caching of processing stage results.
Provides idempotent operations by checking content hashes before re-processing.
"""
import hashlib
import json
from typing import Optional, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.processing_cache import ProcessingCache
from app.services.database import db_manager

logger = logging.getLogger(__name__)


class ProcessingCacheService:
    """
    Service for managing processing cache entries.

    This service enables idempotent processing by:
    1. Computing content hashes for each stage input
    2. Checking if the same content has been processed before
    3. Returning cached results if available
    4. Storing new results for future reuse
    """

    @staticmethod
    def compute_content_hash(content: Any) -> str:
        """
        Compute SHA256 hash of content.

        Args:
            content: Can be bytes, str, dict, or any JSON-serializable object

        Returns:
            SHA256 hash as hex string
        """
        if isinstance(content, bytes):
            data = content
        elif isinstance(content, str):
            data = content.encode('utf-8')
        else:
            # For dicts, lists, etc., serialize to JSON first
            data = json.dumps(content, sort_keys=True).encode('utf-8')

        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def compute_cache_key(content_hash: str, stage: str) -> str:
        """
        Compute unique cache key from content hash and stage.

        Args:
            content_hash: SHA256 hash of content
            stage: Processing stage name

        Returns:
            Cache key (SHA256 hash of content_hash + stage)
        """
        key_input = f"{content_hash}:{stage}"
        return hashlib.sha256(key_input.encode('utf-8')).hexdigest()

    async def get_cached_result(
        self,
        content_hash: str,
        stage: str,
        document_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None
    ) -> Optional[dict]:
        """
        Get cached result for a given content hash and stage.

        Args:
            content_hash: SHA256 hash of the input content
            stage: Processing stage name
            document_id: Optional document ID to filter by
            db: Optional database session (creates new one if not provided)

        Returns:
            Cached result_data as dict, or None if not found
        """
        cache_key = self.compute_cache_key(content_hash, stage)

        async def _get(session: AsyncSession) -> Optional[dict]:
            query = select(ProcessingCache).where(ProcessingCache.cache_key == cache_key)
            if document_id is not None:
                query = query.where(ProcessingCache.document_id == document_id)
            result = await session.execute(query)
            cache_entry = result.scalar_one_or_none()

            if cache_entry:
                logger.info(f"Cache HIT for stage={stage}, cache_key={cache_key}...")
                return cache_entry.result_data
            else:
                logger.info(f"Cache MISS for stage={stage}, cache_key={cache_key}...")
                return None

        if db:
            return await _get(db)
        else:
            async with db_manager.session() as session:
                return await _get(session)

    async def set_cached_result(
        self,
        content_hash: str,
        stage: str,
        result_data: dict,
        document_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
        db: Optional[AsyncSession] = None
    ) -> ProcessingCache:
        """
        Store a processing result in cache.

        Args:
            content_hash: SHA256 hash of the input content
            stage: Processing stage name
            result_data: Result data to cache (must be JSON-serializable)
            document_id: Optional document ID for tracking
            metadata: Optional metadata about the processing
            db: Optional database session (creates new one if not provided)

        Returns:
            Created ProcessingCache entry
        """
        cache_key = self.compute_cache_key(content_hash, stage)

        async def _set(session: AsyncSession) -> ProcessingCache:
            # Check if entry already exists
            result = await session.execute(
                select(ProcessingCache).where(ProcessingCache.cache_key == cache_key)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing entry
                logger.info(f"Updating cache entry for stage={stage}, cache_key={cache_key}...")
                existing.result_data = result_data
                existing.processing_metadata = metadata
                existing.document_id = document_id
                await session.commit()
                await session.refresh(existing)
                return existing
            else:
                # Create new entry
                logger.info(f"Creating cache entry for stage={stage}, cache_key={cache_key}...")
                cache_entry = ProcessingCache(
                    cache_key=cache_key,
                    stage=stage,
                    content_hash=content_hash,
                    result_data=result_data,
                    processing_metadata=metadata,
                    document_id=document_id
                )
                session.add(cache_entry)
                await session.commit()
                await session.refresh(cache_entry)
                return cache_entry

        if db:
            return await _set(db)
        else:
            async with db_manager.session() as session:
                return await _set(session)

    async def invalidate_cache(
        self,
        content_hash: Optional[str] = None,
        stage: Optional[str] = None,
        document_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None
    ) -> int:
        """
        Invalidate cache entries matching the criteria.

        Args:
            content_hash: Filter by content hash
            stage: Filter by stage
            document_id: Filter by document ID
            db: Optional database session

        Returns:
            Number of entries deleted
        """
        async def _invalidate(session: AsyncSession) -> int:
            query = select(ProcessingCache)

            if content_hash:
                query = query.where(ProcessingCache.content_hash == content_hash)
            if stage:
                query = query.where(ProcessingCache.stage == stage)
            if document_id:
                query = query.where(ProcessingCache.document_id == document_id)

            result = await session.execute(query)
            entries = result.scalars().all()

            count = len(entries)
            for entry in entries:
                await session.delete(entry)

            await session.commit()
            logger.info(f"Invalidated {count} cache entries")
            return count

        if db:
            return await _invalidate(db)
        else:
            async with db_manager.session() as session:
                return await _invalidate(session)


# Global singleton instance
processing_cache_service = ProcessingCacheService()
