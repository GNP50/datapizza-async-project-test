from enum import Enum as PyEnum
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, Enum, UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID
from typing import Optional  # Add this import

from .base import Base, TimestampMixin, UUIDMixin


class DocumentProcessingState(str, PyEnum):
    """Processing states for document pipeline"""
    PENDING = "pending"
    OCR_EXTRACTION = "ocr_extraction"
    FACT_ATOMIZATION = "fact_atomization"
    WEB_VERIFICATION = "web_verification"
    QA_GENERATION = "qa_generation"
    VECTOR_INDEXING = "vector_indexing"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def active_states(cls) -> set["DocumentProcessingState"]:
        """States indicating a document is currently being processed by a worker."""
        return {
            cls.OCR_EXTRACTION,
            cls.FACT_ATOMIZATION,
            cls.WEB_VERIFICATION,
            cls.QA_GENERATION,
            cls.VECTOR_INDEXING,
            cls.PENDING
        }


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    chat_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    message_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracted_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_state: Mapped[DocumentProcessingState] = mapped_column(
        Enum(DocumentProcessingState),
        default=DocumentProcessingState.PENDING,
        nullable=False,
        index=True
    )
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    chat: Mapped["Chat"] = relationship("Chat", back_populates="documents")
    message: Mapped[Optional["Message"]] = relationship("Message", back_populates="documents")
    facts: Mapped[list["Fact"]] = relationship(
        "Fact",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    processing_caches: Mapped[list["ProcessingCache"]] = relationship(
        "ProcessingCache",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    flashcards: Mapped[list["Flashcard"]] = relationship(
        "Flashcard",
        back_populates="document",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, processed={self.processed})>"