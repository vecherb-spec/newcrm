from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.installations.models import (
    CrewMember,
    CrewRole,
    InstallationJob,
    InstallationStatus,
)

router = APIRouter(prefix="/installations", tags=["Installations"])


class CrewMemberCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    role: CrewRole


class CrewMemberRead(CrewMemberCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ChecklistItem(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    done: bool = False


class InstallationCreate(BaseModel):
    project_id: UUID
    lead_id: UUID | None = None
    title: str = Field(min_length=2, max_length=255)
    address: str = Field(min_length=2)
    starts_at: datetime
    ends_at: datetime
    status: InstallationStatus = InstallationStatus.SCHEDULED
    notes: str | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list)
    crew_member_ids: list[UUID] = Field(default_factory=list)


class InstallationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    address: str | None = Field(default=None, min_length=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: InstallationStatus | None = None
    notes: str | None = None
    checklist: list[ChecklistItem] | None = None
    crew_member_ids: list[UUID] | None = None


class CrewConflict(BaseModel):
    crew_member_id: UUID
    crew_member_name: str
    conflicting_job_id: UUID
    conflicting_job_title: str
    starts_at: datetime
    ends_at: datetime


class InstallationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    lead_id: UUID | None
    title: str
    address: str
    starts_at: datetime
    ends_at: datetime
    status: InstallationStatus
    notes: str | None
    checklist: list[dict[str, object]]
    crew: list[CrewMemberRead]
    conflicts: list[CrewConflict] = Field(default_factory=list)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _intervals_overlap(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


async def _load_crew(session: AsyncSession, crew_ids: list[UUID]) -> list[CrewMember]:
    if not crew_ids:
        return []
    members = list(
        await session.scalars(select(CrewMember).where(CrewMember.id.in_(crew_ids)))
    )
    if len(members) != len(set(crew_ids)):
        raise HTTPException(status_code=404, detail="Участник бригады не найден")
    return members


async def _detect_conflicts(
    session: AsyncSession,
    *,
    crew_ids: list[UUID],
    starts_at: datetime,
    ends_at: datetime,
    exclude_job_id: UUID | None = None,
) -> list[CrewConflict]:
    if not crew_ids:
        return []
    starts_at = _ensure_aware(starts_at)
    ends_at = _ensure_aware(ends_at)
    statement = (
        select(InstallationJob, CrewMember)
        .join(InstallationJob.crew)
        .where(
            CrewMember.id.in_(crew_ids),
            InstallationJob.status != InstallationStatus.COMPLETED,
        )
    )
    if exclude_job_id:
        statement = statement.where(InstallationJob.id != exclude_job_id)
    conflicts: list[CrewConflict] = []
    for job, member in await session.execute(statement):
        if _intervals_overlap(
            starts_at,
            ends_at,
            _ensure_aware(job.starts_at),
            _ensure_aware(job.ends_at),
        ):
            conflicts.append(
                CrewConflict(
                    crew_member_id=member.id,
                    crew_member_name=member.name,
                    conflicting_job_id=job.id,
                    conflicting_job_title=job.title,
                    starts_at=job.starts_at,
                    ends_at=job.ends_at,
                )
            )
    return conflicts


def _serialize_job(job: InstallationJob, conflicts: list[CrewConflict]) -> InstallationRead:
    payload = InstallationRead.model_validate(job)
    payload.conflicts = conflicts
    return payload


@router.get("/crew", response_model=list[CrewMemberRead])
async def list_crew(session: AsyncSession = Depends(get_session)) -> list[CrewMember]:
    return list(await session.scalars(select(CrewMember).order_by(CrewMember.name)))


@router.post("/crew", response_model=CrewMemberRead, status_code=status.HTTP_201_CREATED)
async def create_crew_member(
    payload: CrewMemberCreate,
    session: AsyncSession = Depends(get_session),
) -> CrewMember:
    member = CrewMember(**payload.model_dump())
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/jobs", response_model=list[InstallationRead])
async def list_installations(
    project_id: UUID | None = None,
    status_filter: InstallationStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[InstallationRead]:
    statement = select(InstallationJob).options(selectinload(InstallationJob.crew))
    if project_id:
        statement = statement.where(InstallationJob.project_id == project_id)
    if status_filter:
        statement = statement.where(InstallationJob.status == status_filter)
    statement = statement.order_by(InstallationJob.starts_at.desc())
    jobs = list(await session.scalars(statement))
    result: list[InstallationRead] = []
    for job in jobs:
        conflicts = await _detect_conflicts(
            session,
            crew_ids=[member.id for member in job.crew],
            starts_at=job.starts_at,
            ends_at=job.ends_at,
            exclude_job_id=job.id,
        )
        result.append(_serialize_job(job, conflicts))
    return result


@router.get("/calendar", response_model=list[InstallationRead])
async def installation_calendar(
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[InstallationRead]:
    start = _ensure_aware(start)
    end = _ensure_aware(end)
    jobs = list(
        await session.scalars(
            select(InstallationJob)
            .options(selectinload(InstallationJob.crew))
            .where(
                InstallationJob.starts_at < end,
                InstallationJob.ends_at > start,
            )
            .order_by(InstallationJob.starts_at)
        )
    )
    result: list[InstallationRead] = []
    for job in jobs:
        conflicts = await _detect_conflicts(
            session,
            crew_ids=[member.id for member in job.crew],
            starts_at=job.starts_at,
            ends_at=job.ends_at,
            exclude_job_id=job.id,
        )
        result.append(_serialize_job(job, conflicts))
    return result


@router.post("/jobs", response_model=InstallationRead, status_code=status.HTTP_201_CREATED)
async def create_installation(
    payload: InstallationCreate,
    session: AsyncSession = Depends(get_session),
) -> InstallationRead:
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="Окончание должно быть позже начала")
    conflicts = await _detect_conflicts(
        session,
        crew_ids=payload.crew_member_ids,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    job = InstallationJob(
        project_id=payload.project_id,
        lead_id=payload.lead_id,
        title=payload.title,
        address=payload.address,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=payload.status,
        notes=payload.notes,
        checklist=[item.model_dump() for item in payload.checklist],
    )
    job.crew = await _load_crew(session, payload.crew_member_ids)
    session.add(job)
    await session.commit()
    await session.refresh(job, attribute_names=["crew"])
    return _serialize_job(job, conflicts)


@router.patch("/jobs/{job_id}", response_model=InstallationRead)
async def update_installation(
    job_id: UUID,
    payload: InstallationUpdate,
    session: AsyncSession = Depends(get_session),
) -> InstallationRead:
    job = await session.scalar(
        select(InstallationJob)
        .where(InstallationJob.id == job_id)
        .options(selectinload(InstallationJob.crew))
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Монтаж не найден")
    data = payload.model_dump(exclude_unset=True)
    crew_ids = data.pop("crew_member_ids", None)
    for field, value in data.items():
        if field == "checklist" and value is not None:
            setattr(job, field, [ChecklistItem.model_validate(item).model_dump() for item in value])
        else:
            setattr(job, field, value)
    if crew_ids is not None:
        job.crew = await _load_crew(session, crew_ids)
    if job.ends_at <= job.starts_at:
        raise HTTPException(status_code=422, detail="Окончание должно быть позже начала")
    conflicts = await _detect_conflicts(
        session,
        crew_ids=[member.id for member in job.crew],
        starts_at=job.starts_at,
        ends_at=job.ends_at,
        exclude_job_id=job.id,
    )
    await session.commit()
    await session.refresh(job, attribute_names=["crew"])
    return _serialize_job(job, conflicts)
