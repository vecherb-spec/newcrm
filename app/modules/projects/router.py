from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.projects.models import Project, ProjectStatus

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    lead_id: UUID | None = None
    installation_date: date | None = None
    installation_address: str | None = None


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: ProjectStatus
    delivery_status: str


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return list(await session.scalars(select(Project).order_by(Project.created_at.desc())))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    project = Project(**payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project
