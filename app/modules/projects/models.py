from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin


class ProjectStatus(StrEnum):
    PLANNING = "PLANNING"
    PROCUREMENT = "PROCUREMENT"
    PRODUCTION = "PRODUCTION"
    DELIVERY = "DELIVERY"
    INSTALLATION = "INSTALLATION"
    COMMISSIONING = "COMMISSIONING"
    COMPLETED = "COMPLETED"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


class Project(UUIDTimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255))
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), unique=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.PLANNING
    )
    installation_date: Mapped[date | None] = mapped_column(Date)
    installation_address: Mapped[str | None] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(50), default="pending")
    calculation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("engineering_calculations.id"), index=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tasks: Mapped[list["ProjectTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    notes: Mapped[list["ProjectNote"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectNote.occurred_at.desc()",
    )


class ProjectNote(UUIDTimestampMixin, Base):
    __tablename__ = "project_notes"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    project: Mapped["Project"] = relationship(back_populates="notes")


class ProjectTask(UUIDTimestampMixin, Base):
    __tablename__ = "project_tasks"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    assignee: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.TODO)
    due_date: Mapped[date | None] = mapped_column(Date)
    project: Mapped[Project] = relationship(back_populates="tasks")
