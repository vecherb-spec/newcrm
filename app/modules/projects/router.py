from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.crm.models import Lead, LeadStatus
from app.modules.projects.models import (
    Project,
    ProjectStatus,
    ProjectTask,
    TaskStatus,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

DEFAULT_TASKS = (
    "Сварка металлокаркаса",
    "Комплектация и доставка модулей",
    "Монтаж на объекте",
    "Пусконаладка и настройка",
    "Подписание акта приёмки",
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    lead_id: UUID | None = None
    installation_date: date | None = None
    installation_address: str | None = None
    create_default_tasks: bool = True


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    assignee: str | None = Field(default=None, max_length=160)
    due_date: date | None = None


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    assignee: str | None = Field(default=None, max_length=160)
    due_date: date | None = None


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: TaskStatus


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    lead_id: UUID | None
    status: ProjectStatus
    delivery_status: str
    installation_date: date | None
    installation_address: str | None
    tasks: list[TaskRead]


class ProjectUpdate(BaseModel):
    status: ProjectStatus | None = None
    delivery_status: str | None = Field(default=None, max_length=50)
    installation_date: date | None = None
    installation_address: str | None = None


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    query = (
        select(Project)
        .options(selectinload(Project.tasks))
        .order_by(Project.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    if payload.lead_id:
        lead = await session.get(Lead, payload.lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        if lead.status is not LeadStatus.CLOSED_WON:
            raise HTTPException(
                status_code=409,
                detail="Project can only be created from a won lead",
            )
    data = payload.model_dump(exclude={"create_default_tasks"})
    project = Project(**data)
    if payload.create_default_tasks:
        project.tasks = [ProjectTask(title=title) for title in DEFAULT_TASKS]
    session.add(project)
    await session.commit()
    await session.refresh(project, attribute_names=["tasks"])
    return project


async def _get_project(project_id: UUID, session: AsyncSession) -> Project:
    project = await session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.tasks))
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    project = await _get_project(project_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    return project


@router.post(
    "/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    project_id: UUID,
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),
) -> ProjectTask:
    await _get_project(project_id, session)
    task = ProjectTask(project_id=project_id, **payload.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{project_id}/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    project_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    session: AsyncSession = Depends(get_session),
) -> ProjectTask:
    task = await session.scalar(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task
