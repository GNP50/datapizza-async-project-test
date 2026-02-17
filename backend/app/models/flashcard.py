from enum import Enum as PyEnum
from sqlalchemy import String, Float, Integer, Text, ForeignKey, Enum, UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID
from typing import Optional

from .base import Base, TimestampMixin, UUIDMixin


class FlashcardStatus(str, PyEnum):
    """Status of flashcard generation for a document"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Flashcard(Base, UUIDMixin, TimestampMixin):
    """
    Flashcards generated from document facts.
    Each flashcard has a front (question/prompt) and back (answer) side.
    """
    __tablename__ = "flashcards"

    document_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    fact_id: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("facts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Flashcard content
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)

    # Category/type of flashcard (definition, concept, date, etc.)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Difficulty level (1-5, estimated by LLM)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Confidence score from generation (0.0 to 1.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="flashcards")
    fact: Mapped[Optional["Fact"]] = relationship("Fact")

    def __repr__(self) -> str:
        return f"<Flashcard(id={self.id}, category={self.category}, difficulty={self.difficulty})>"
