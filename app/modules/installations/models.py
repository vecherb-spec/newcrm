from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDTimestampMixin


class CrewRole(StrEnum):
    INSTALLER = "INSTALLER"
    ENGINEER = "ENGINEER"
    DRIVER = "DRIVER"
    CONTRACTOR = "CONTRACTOR"


class InstallationStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RESCHEDULED = "RESCHEDULED"


installation_job_crew = Table(
    "installation_job_crew",
    Base.metadata,
    Column("job_id", ForeignKey("installation_jobs.id"), primary_key=True),
    Column("crew_member_id", ForeignKey("crew_members.id"), primary_key=True),
)


class CrewMember(UUIDTimestampMixin, Base):
    __tablename__ = "crew_members"

    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    role: Mapped[CrewRole] = mapped_column(Enum(CrewRole))
    jobs: Mapped[list["InstallationJob"]] = relationship(
        secondary=installation_job_crew,
        back_populates="crew",
    )


class InstallationJob(UUIDTimestampMixin, Base):
    __tablename__ = "installation_jobs"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[InstallationStatus] = mapped_column(
        Enum(InstallationStatus), default=InstallationStatus.SCHEDULED
    )
    notes: Mapped[str | None] = mapped_column(Text)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    crew: Mapped[list[CrewMember]] = relationship(
        secondary=installation_job_crew,
        back_populates="jobs",
    )
