from sqlalchemy import Text, Float, Integer, String, ForeignKey, Enum, UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID
from typing import Optional

from .base import Base, TimestampMixin, UUIDMixin
from .fact_check import VerificationStatus  # Reuse existing enum to avoid conflicts


class Fact(Base, UUIDMixin, TimestampMixin):
    """
    Atomic facts extracted from documents.
    Each fact represents a single verifiable claim from the PDF content.
    """
    __tablename__ = "facts"

    document_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # The atomic fact content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Source reference within the document
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Verification status from web search
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False,
        index=True
    )

    # URL found via web search that validates/debunks the fact
    web_source_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Confidence score from verification (0.0 to 1.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Optional: reasoning or additional context from verification
    verification_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="facts")

    def __repr__(self) -> str:
        return f"<Fact(id={self.id}, page={self.page_number}, status={self.verification_status})>"
