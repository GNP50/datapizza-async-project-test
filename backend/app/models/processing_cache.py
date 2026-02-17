"""
Processing Cache Model - Stores cached results of processing stages.
Enables idempotent operations by caching results keyed by content hash.
"""
from sqlalchemy import Column, String, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base, UUIDMixin, TimestampMixin


class ProcessingCache(Base, UUIDMixin, TimestampMixin):
    """
    Cache table for storing processing stage results.

    Each cache entry represents a completed processing stage for a specific content.
    The cache_key is unique and combines content_hash + stage for fast lookups.

    Attributes:
        cache_key: Unique key for this cache entry (hash of content_hash + stage)
        stage: Processing stage name (e.g., 'ocr', 'fact_extraction', 'web_verification', 'qa_generation')
        document_id: Optional reference to the document (for tracking)
        content_hash: SHA256 hash of the input content for this stage
        result_data: JSON-serialized result of the processing stage
        processing_metadata: Optional metadata about the processing (e.g., method, page_count, confidence)
    """
    __tablename__ = "processing_cache"

    cache_key = Column(String(64), nullable=False, unique=True, index=True)
    stage = Column(String(50), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    content_hash = Column(String(64), nullable=False)
    result_data = Column(JSON, nullable=False)
    processing_metadata = Column(JSON, nullable=True)

    # Relationship
    document = relationship("Document", back_populates="processing_caches")

    # Composite index for efficient lookups by content_hash + stage
    __table_args__ = (
        Index('ix_processing_cache_content_hash_stage', 'content_hash', 'stage'),
    )

    def __repr__(self):
        return f"<ProcessingCache(stage={self.stage}, cache_key={self.cache_key}...)>"
