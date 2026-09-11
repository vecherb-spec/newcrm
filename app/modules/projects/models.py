from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin


class ProjectStatus(StrEnum):
    PLANNING = "PLANNING"
    PROCUREMENT = "PROCUREMENT"
    PRODUCTION = "PRODUCTION"
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
    tasks: Mapped[list["ProjectTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectTask(UUIDTimestampMixin, Base):
    __tablename__ = "project_tasks"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    assignee: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.TODO)
    due_date: Mapped[date | None] = mapped_column(Date)
    project: Mapped[Project] = relationship(back_populates="tasks")
