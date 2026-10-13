from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.calculator.models import EngineeringCalculation
from app.modules.crm.models import Lead, LeadStatus
from app.modules.projects.models import Project, ProjectStatus, ProjectTask

DEFAULT_TASKS = (
    "Сварка металлокаркаса",
    "Комплектация и доставка модулей",
    "Монтаж на объекте",
    "Пусконаладка и настройка",
    "Подписание акта приёмки",
)


def lead_ready_for_project(lead: Lead) -> bool:
    return (
        lead.status is LeadStatus.CLOSED_WON
        and lead.contract_signed
        and lead.paid
    )


async def latest_calculation_id(session: AsyncSession, lead_id: UUID) -> UUID | None:
    return await session.scalar(
        select(EngineeringCalculation.id)
        .where(EngineeringCalculation.lead_id == lead_id)
        .order_by(EngineeringCalculation.created_at.desc())
    )


async def get_project_for_lead(session: AsyncSession, lead_id: UUID) -> Project | None:
    return await session.scalar(
        select(Project)
        .where(Project.lead_id == lead_id)
        .options(selectinload(Project.tasks), selectinload(Project.notes))
    )


async def create_project_from_lead(
    session: AsyncSession,
    lead: Lead,
    *,
    create_default_tasks: bool = True,
) -> Project:
    existing = await get_project_for_lead(session, lead.id)
    if existing:
        return existing
    if lead.status is not LeadStatus.CLOSED_WON:
        raise ValueError("Проект можно создать только из выигранной сделки")
    calculation_id = await latest_calculation_id(session, lead.id)
    project = Project(
        name=lead.title,
        lead_id=lead.id,
        status=ProjectStatus.PROCUREMENT,
        installation_address=None,
        calculation_id=calculation_id,
        amount=lead.amount,
    )
    if create_default_tasks:
        project.tasks = [ProjectTask(title=title) for title in DEFAULT_TASKS]
    session.add(project)
    await session.flush()
    return project


async def maybe_auto_create_project(session: AsyncSession, lead: Lead) -> Project | None:
    if not lead_ready_for_project(lead):
        return None
    return await create_project_from_lead(session, lead)
