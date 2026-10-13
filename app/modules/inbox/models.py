from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin
from app.modules.auth.models import User
from app.modules.crm.models import Contact, Lead


class InboxChannel(StrEnum):
    RADIST = "RADIST"
    EMAIL = "EMAIL"
    VK = "VK"
    TELEGRAM_LEGACY = "TELEGRAM_LEGACY"
    MAX_LEGACY = "MAX_LEGACY"


class MessageDirection(StrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class MessageStatus(StrEnum):
    RECEIVED = "RECEIVED"
    SENT = "SENT"
    FAILED = "FAILED"


class InboxConversation(UUIDTimestampMixin, Base):
    __tablename__ = "inbox_conversations"

    channel: Mapped[InboxChannel] = mapped_column(Enum(InboxChannel), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    contact: Mapped[Contact | None] = relationship()
    lead: Mapped[Lead | None] = relationship()
    messages: Mapped[list["InboxMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="InboxMessage.created_at.asc()",
    )


class InboxMessage(UUIDTimestampMixin, Base):
    __tablename__ = "inbox_messages"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("inbox_conversations.id"), index=True)
    channel: Mapped[InboxChannel] = mapped_column(Enum(InboxChannel), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection), index=True)
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus),
        default=MessageStatus.RECEIVED,
    )
    body: Mapped[str | None] = mapped_column(Text)
    sender_name: Mapped[str | None] = mapped_column(String(160))
    sent_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    attachment_url: Mapped[str | None] = mapped_column(Text)
    attachment_mime: Mapped[str | None] = mapped_column(String(120))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    conversation: Mapped[InboxConversation] = relationship(back_populates="messages")
    sent_by: Mapped[User | None] = relationship()
