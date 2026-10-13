from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.auth.router import CurrentUser
from app.modules.crm.models import Lead, LeadStatus
from app.modules.crm.schemas import ContactRead
from app.modules.finance.router import ProjectEconomics, project_economics
from app.modules.installations.models import InstallationJob
from app.modules.inventory.service import list_project_reservations
from app.modules.projects.models import (
    Project,
    ProjectNote,
    ProjectStatus,
    ProjectTask,
    TaskStatus,
)
from app.modules.projects.service import (
    create_project_from_lead,
    get_project_for_lead,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


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


class ProjectNoteCreate(BaseModel):
    body: str = Field(min_length=1)


class ProjectNoteRead(ProjectNoteCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    author_id: UUID
    occurred_at: datetime


class ReservedStockItem(BaseModel):
    sku_id: UUID
    code: str
    name: str
    quantity: Decimal
    unit: str


class InstallationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    address: str
    starts_at: datetime
    ends_at: datetime
    status: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    lead_id: UUID | None
    status: ProjectStatus
    delivery_status: str
    installation_date: date | None
    installation_address: str | None
    calculation_id: UUID | None
    amount: Decimal | None
    tasks: list[TaskRead]


class ProjectDetail(ProjectRead):
    contact: ContactRead | None = None
    notes: list[ProjectNoteRead] = Field(default_factory=list)
    reserved_stock: list[ReservedStockItem] = Field(default_factory=list)
    installations: list[InstallationSummary] = Field(default_factory=list)
    economics: ProjectEconomics | None = None


class ProjectBoard(BaseModel):
    columns: dict[str, list[ProjectRead]]


class ProjectUpdate(BaseModel):
    status: ProjectStatus | None = None
    delivery_status: str | None = Field(default=None, max_length=50)
    installation_date: date | None = None
    installation_address: str | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    query = select(Project).options(selectinload(Project.tasks)).order_by(Project.created_at.desc())
    return list(await session.scalars(query))


@router.get("/board", response_model=ProjectBoard)
async def project_board(session: AsyncSession = Depends(get_session)) -> ProjectBoard:
    projects = list(
        await session.scalars(select(Project).options(selectinload(Project.tasks)))
    )
    columns: dict[str, list[ProjectRead]] = {status.value: [] for status in ProjectStatus}
    for project in projects:
        columns[project.status.value].append(ProjectRead.model_validate(project))
    return ProjectBoard(columns=columns)


@router.get("/by-lead/{lead_id}", response_model=ProjectRead | None)
async def project_by_lead(
    lead_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Project | None:
    return await get_project_for_lead(session, lead_id)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    if payload.lead_id:
        lead = await session.get(Lead, payload.lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        if lead.status != LeadStatus.CLOSED_WON.value:
            raise HTTPException(
                status_code=409,
                detail="Project can only be created from a won lead",
            )
        project = await create_project_from_lead(
            session,
            lead,
            create_default_tasks=payload.create_default_tasks,
        )
        if payload.installation_date:
            project.installation_date = payload.installation_date
        if payload.installation_address:
            project.installation_address = payload.installation_address
        if payload.name and payload.name != lead.title:
            project.name = payload.name
    else:
        data = payload.model_dump(exclude={"create_default_tasks"})
        project = Project(**data)
        if payload.create_default_tasks:
            from app.modules.projects.service import DEFAULT_TASKS

            project.tasks = [ProjectTask(title=title) for title in DEFAULT_TASKS]
        session.add(project)
    await session.commit()
    await session.refresh(project, attribute_names=["tasks"])
    return project


@router.post(
    "/from-lead/{lead_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_from_lead_endpoint(
    lead_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Project:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    try:
        project = await create_project_from_lead(session, lead)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await session.commit()
    await session.refresh(project, attribute_names=["tasks"])
    return project


async def _get_project(project_id: UUID, session: AsyncSession) -> Project:
    project = await session.scalar(
        select(Project).where(Project.id == project_id).options(selectinload(Project.tasks))
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project_detail(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ProjectDetail:
    project = await session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.tasks), selectinload(Project.notes))
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    contact = None
    if project.lead_id:
        lead = await session.scalar(
            select(Lead).where(Lead.id == project.lead_id).options(selectinload(Lead.contact))
        )
        if lead and lead.contact:
            contact = ContactRead.model_validate(lead.contact)
    reserved = [
        ReservedStockItem(
            sku_id=sku.id,
            code=sku.code,
            name=sku.name,
            quantity=quantity,
            unit=sku.unit,
        )
        for sku, quantity in await list_project_reservations(session, project.id)
    ]
    installations = list(
        await session.scalars(
            select(InstallationJob)
            .where(InstallationJob.project_id == project.id)
            .order_by(InstallationJob.starts_at.desc())
        )
    )
    economics = await project_economics(project.id, session)
    return ProjectDetail(
        **ProjectRead.model_validate(project).model_dump(),
        contact=contact,
        notes=[ProjectNoteRead.model_validate(note) for note in project.notes],
        reserved_stock=reserved,
        installations=[InstallationSummary.model_validate(item) for item in installations],
        economics=economics,
    )


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
    "/{project_id}/notes",
    response_model=ProjectNoteRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_project_note(
    project_id: UUID,
    payload: ProjectNoteCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ProjectNote:
    await _get_project(project_id, session)
    note = ProjectNote(project_id=project_id, author_id=actor.id, body=payload.body)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


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
