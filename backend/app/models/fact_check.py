from enum import Enum as PyEnum
from sqlalchemy import Text, Float, ForeignKey, Enum, JSON, UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Any
from uuid import UUID

from .base import Base, TimestampMixin, UUIDMixin


class VerificationStatus(str, PyEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    DEBUNKED = "debunked"
    UNCERTAIN = "uncertain"


class FactCheck(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "fact_checks"

    message_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sources: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="fact_checks")

    def __repr__(self) -> str:
        return f"<FactCheck(id={self.id}, status={self.verification_status}, score={self.confidence_score})>"
