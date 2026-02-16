from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID

from sqlalchemy import JSON
from sqlalchemy import UUID as SQLUUID
from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ProcessingState(str, PyEnum):
    """
    State machine for document processing pipeline.
    Each state represents a stage in the fact-checking and semantic cache architecture.
    """
    PENDING = "pending"

    # Stage A: OCR & Extraction
    OCR_EXTRACTION = "ocr_extraction"

    # Stage B: Fact Atomization
    FACT_ATOMIZATION = "fact_atomization"

    # Stage C: Web Verification
    WEB_VERIFICATION = "web_verification"

    # Stage D: Q&A Generation (Semantic Cache Preparation)
    QA_GENERATION = "qa_generation"

    # Stage E: Vector Store Indexing
    VECTOR_INDEXING = "vector_indexing"

    # Final states
    GENERATING_RESPONSE = "generating_response"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def active_states(cls) -> set["ProcessingState"]:
        """States indicating a message is currently being processed by a worker."""
        return {
            cls.OCR_EXTRACTION,
            cls.FACT_ATOMIZATION,
            cls.WEB_VERIFICATION,
            cls.QA_GENERATION,
            cls.VECTOR_INDEXING,
            cls.GENERATING_RESPONSE,
            cls.PENDING
        }


class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    chat_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    processing_state: Mapped[ProcessingState] = mapped_column(
        Enum(ProcessingState),
        default=ProcessingState.PENDING,
        nullable=False,
        index=True
    )

    # Response generation metadata
    response_cached: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    response_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    response_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    fact_checks: Mapped[list["FactCheck"]] = relationship(
        "FactCheck",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="message",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role}, state={self.processing_state})>"
