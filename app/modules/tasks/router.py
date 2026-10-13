from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.auth.models import User
from app.modules.auth.router import CurrentUser
from app.modules.crm.models import (
    Contact,
    Lead,
    LeadStatus,
    LeadTask,
    TaskPriority,
    TaskStatus,
)
from app.modules.crm.schemas import ContactRead, LeadRead, UserSummary
from app.modules.tasks.service import ensure_aware, utc_now

router = APIRouter(prefix="/tasks", tags=["Tasks"])
TaskView = Literal["today", "overdue", "week", "all"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    due_at: datetime | None = None
    responsible_user_id: UUID | None = None
    lead_id: UUID | None = None
    contact_id: UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    due_at: datetime | None = None
    responsible_user_id: UUID | None = None
    lead_id: UUID | None = None
    contact_id: UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    is_completed: bool | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    due_at: datetime | None
    status: TaskStatus
    priority: TaskPriority
    is_completed: bool
    completed_at: datetime | None
    kind: str
    lead_id: UUID | None
    contact_id: UUID | None
    responsible_user_id: UUID | None
    author_id: UUID
    lead: LeadRead | None = None
    contact: ContactRead | None = None
    responsible_user: UserSummary | None = None
    author: UserSummary | None = None
    created_at: datetime


class TaskDashboard(BaseModel):
    today: int
    overdue: int
    week: int
    no_response_proposals: int


class ProposalNoResponse(BaseModel):
    lead_id: UUID
    title: str
    contact_name: str | None
    last_activity_at: datetime
    days_without_activity: int
    flag: str = "КП без ответа"


def _task_options() -> tuple[object, ...]:
    return (
        selectinload(LeadTask.lead).selectinload(Lead.contact),
        selectinload(LeadTask.contact),
        selectinload(LeadTask.responsible_user),
        selectinload(LeadTask.author),
    )


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def _validate_links(payload: TaskCreate | TaskUpdate, session: AsyncSession) -> None:
    if payload.responsible_user_id and await session.get(User, payload.responsible_user_id) is None:
        raise HTTPException(status_code=404, detail="Ответственный пользователь не найден")
    if payload.lead_id and await session.get(Lead, payload.lead_id) is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if payload.contact_id and await session.get(Contact, payload.contact_id) is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")


def _apply_completion(task: LeadTask, is_completed: bool) -> None:
    task.is_completed = is_completed
    task.status = TaskStatus.DONE if is_completed else TaskStatus.TODO
    task.completed_at = utc_now() if is_completed else None


async def _proposal_flags(session: AsyncSession) -> list[ProposalNoResponse]:
    cutoff = utc_now() - timedelta(days=3)
    leads = list(
        await session.scalars(
            select(Lead)
            .where(Lead.status == LeadStatus.PROPOSAL_SENT)
            .options(selectinload(Lead.activities), selectinload(Lead.contact))
        )
    )
    result: list[ProposalNoResponse] = []
    for lead in leads:
        last_activity = max(
            (ensure_aware(activity.occurred_at) for activity in lead.activities),
            default=ensure_aware(lead.created_at),
        )
        if last_activity <= cutoff:
            result.append(
                ProposalNoResponse(
                    lead_id=lead.id,
                    title=lead.title,
                    contact_name=lead.contact.name if lead.contact else None,
                    last_activity_at=last_activity,
                    days_without_activity=(utc_now() - last_activity).days,
                )
            )
    return result


def _filter_by_view(statement: object, view: TaskView) -> object:
    now = utc_now()
    today_start, tomorrow_start = _day_bounds(now.date())
    if view == "today":
        return statement.where(LeadTask.due_at >= today_start, LeadTask.due_at < tomorrow_start)
    if view == "overdue":
        return statement.where(LeadTask.due_at < now, LeadTask.status != TaskStatus.DONE)
    if view == "week":
        return statement.where(
            LeadTask.due_at >= today_start,
            LeadTask.due_at < today_start + timedelta(days=7),
        )
    return statement


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    view: TaskView = "today",
    responsible_user_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[LeadTask]:
    statement = select(LeadTask).options(*_task_options())
    statement = _filter_by_view(statement, view)
    if responsible_user_id:
        statement = statement.where(LeadTask.responsible_user_id == responsible_user_id)
    statement = statement.order_by(
        LeadTask.due_at.is_(None),
        LeadTask.due_at,
        LeadTask.created_at.desc(),
    )
    return list(await session.scalars(statement))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LeadTask:
    await _validate_links(payload, session)
    contact_id = payload.contact_id
    if payload.lead_id and contact_id is None:
        lead = await session.get(Lead, payload.lead_id)
        contact_id = lead.contact_id if lead else None
    task = LeadTask(
        title=payload.title,
        due_at=payload.due_at,
        priority=payload.priority,
        status=TaskStatus.TODO,
        is_completed=False,
        responsible_user_id=payload.responsible_user_id or actor.id,
        lead_id=payload.lead_id,
        contact_id=contact_id,
        author_id=actor.id,
        kind="manual",
    )
    session.add(task)
    await session.commit()
    return await session.scalar(
        select(LeadTask).where(LeadTask.id == task.id).options(*_task_options())
    )


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    session: AsyncSession = Depends(get_session),
) -> LeadTask:
    await _validate_links(payload, session)
    task = await session.scalar(
        select(LeadTask).where(LeadTask.id == task_id).options(*_task_options())
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    for field, value in payload.model_dump(exclude_unset=True, exclude={"is_completed"}).items():
        setattr(task, field, value)
    if payload.is_completed is not None:
        _apply_completion(task, payload.is_completed)
    elif payload.status is TaskStatus.DONE:
        _apply_completion(task, True)
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/{task_id}/complete", response_model=TaskRead)
async def complete_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> LeadTask:
    task = await session.scalar(
        select(LeadTask).where(LeadTask.id == task_id).options(*_task_options())
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    _apply_completion(task, True)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/dashboard", response_model=TaskDashboard)
async def task_dashboard(session: AsyncSession = Depends(get_session)) -> TaskDashboard:
    today = await list_tasks(view="today", session=session)
    overdue = await list_tasks(view="overdue", session=session)
    week = await list_tasks(view="week", session=session)
    flags = await _proposal_flags(session)
    return TaskDashboard(
        today=len(today),
        overdue=len(overdue),
        week=len(week),
        no_response_proposals=len(flags),
    )


@router.get("/calendar", response_model=list[TaskRead])
async def task_calendar(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[LeadTask]:
    start_date = start or utc_now().date()
    end_date = end or (start_date + timedelta(days=30))
    start_at, _ = _day_bounds(start_date)
    _, end_at = _day_bounds(end_date)
    result = await session.scalars(
        select(LeadTask)
        .where(LeadTask.due_at >= start_at, LeadTask.due_at < end_at)
        .options(*_task_options())
        .order_by(LeadTask.due_at)
    )
    return list(result)


@router.get("/proposal-no-response", response_model=list[ProposalNoResponse])
async def proposal_no_response(
    session: AsyncSession = Depends(get_session),
) -> list[ProposalNoResponse]:
    return await _proposal_flags(session)
