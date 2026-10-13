from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin
from app.modules.auth.models import User


class LeadStatus(StrEnum):
    NEW = "NEW"
    QUALIFICATION = "QUALIFICATION"
    CALCULATION = "CALCULATION"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    NEGOTIATION = "NEGOTIATION"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


class ActivityType(StrEnum):
    CALL = "CALL"
    MESSAGE = "MESSAGE"
    MEETING = "MEETING"
    COMMENT = "COMMENT"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class TaskPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


CRM_TASK_STATUS = Enum(
    TaskStatus,
    name="taskstatuscrm",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
CRM_TASK_PRIORITY = Enum(
    TaskPriority,
    name="taskpriority",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Contact(UUIDTimestampMixin, Base):
    __tablename__ = "contacts"

    amo_id: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(40), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    telegram: Mapped[str | None] = mapped_column(String(160), index=True)
    vk: Mapped[str | None] = mapped_column(String(160), index=True)
    radist_chat_id: Mapped[str | None] = mapped_column(String(80), index=True)


class Lead(UUIDTimestampMixin, Base):
    __tablename__ = "leads"

    amo_id: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    responsible_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    next_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lost_reason: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[Contact | None] = relationship()
    responsible_user: Mapped[User | None] = relationship(foreign_keys=[responsible_user_id])
    activities: Mapped[list["LeadActivity"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="LeadActivity.created_at.desc()",
    )
    tasks: Mapped[list["LeadTask"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="LeadTask.created_at.desc()",
    )


class Message(UUIDTimestampMixin, Base):
    __tablename__ = "messages"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(10), default="in")
    body: Mapped[str] = mapped_column(Text)


class LeadActivity(UUIDTimestampMixin, Base):
    __tablename__ = "lead_activities"

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    type: Mapped[ActivityType] = mapped_column(Enum(ActivityType))
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    lead: Mapped[Lead] = relationship(back_populates="activities")
    author: Mapped[User] = relationship(foreign_keys=[author_id])


class LeadTask(UUIDTimestampMixin, Base):
    __tablename__ = "lead_tasks"

    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[TaskStatus] = mapped_column(CRM_TASK_STATUS, default=TaskStatus.TODO)
    priority: Mapped[TaskPriority] = mapped_column(
        CRM_TASK_PRIORITY, default=TaskPriority.NORMAL
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responsible_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), default="manual")
    auto_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    lead: Mapped[Lead | None] = relationship(back_populates="tasks")
    contact: Mapped[Contact | None] = relationship()
    responsible_user: Mapped[User | None] = relationship(foreign_keys=[responsible_user_id])
    author: Mapped[User] = relationship(foreign_keys=[author_id])
