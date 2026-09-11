import enum
from typing import Any

from sqlalchemy import Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    QUALIFICATION = "QUALIFICATION"
    CALCULATING = "CALCULATING"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    CONTRACT_SIGNING = "CONTRACT_SIGNING"
    IN_PROJECT = "IN_PROJECT"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


class Contact(UUIDTimestampMixin, Base):
    __tablename__ = "contacts"

    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    company: Mapped[str | None] = mapped_column(String(255))


class Lead(UUIDTimestampMixin, Base):
    __tablename__ = "leads"

    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    contact: Mapped[Contact | None] = relationship()


class Message(UUIDTimestampMixin, Base):
    __tablename__ = "messages"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(10), default="in")
    body: Mapped[str] = mapped_column(Text)
