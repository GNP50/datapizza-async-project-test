from sqlalchemy import String, Text, ForeignKey, UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID

from .base import Base, TimestampMixin, UUIDMixin


class Chat(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chats"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="chat",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, user_id={self.user_id}, title={self.title})>"
