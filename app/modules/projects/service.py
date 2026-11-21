from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.calculator.models import EngineeringCalculation
from app.modules.crm.models import Lead, LeadStatus
from app.modules.projects.models import Project, ProjectStatus, ProjectTask

AUTO_PROJECT_STAGE_CODES = frozenset(
    {
        LeadStatus.PREPAYMENT.value,
        LeadStatus.PRODUCTION.value,
    }
)

DEFAULT_TASKS = (
    "Сварка металлокаркаса",
    "Комплектация и доставка модулей",
    "Монтаж на объекте",
    "Пусконаладка и настройка",
    "Подписание акта приёмки",
)


def lead_ready_for_project(lead: Lead) -> bool:
    return bool(lead.contract_signed and lead.paid)


def _address_from_lead_specs(lead: Lead) -> str | None:
    specs = lead.specs or {}
    for key in ("lead_client", "screen", "structure"):
        section = specs.get(key) or {}
        address = section.get("install_address") or section.get("legal_address")
        if address:
            return str(address)
    return None


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
    if not lead_ready_for_project(lead):
        raise ValueError("Проект доступен после подписания договора и оплаты")
    calculation_id = await latest_calculation_id(session, lead.id)
    install_address = _address_from_lead_specs(lead)
    project = Project(
        name=lead.title,
        lead_id=lead.id,
        status=ProjectStatus.PLANNING,
        installation_address=install_address,
        calculation_id=calculation_id,
        amount=lead.amount,
        responsible_user_id=lead.responsible_user_id,
        specs=deepcopy(lead.specs or {}),
        files=deepcopy((lead.specs or {}).get("files") or {}),
    )
    if create_default_tasks:
        project.tasks = [ProjectTask(title=title) for title in DEFAULT_TASKS]
    session.add(project)
    await session.flush()
    return project


async def maybe_auto_create_project(session: AsyncSession, lead: Lead) -> Project | None:
    if not lead_ready_for_project(lead):
        return None
    if lead.status not in AUTO_PROJECT_STAGE_CODES:
        return None
    return await create_project_from_lead(session, lead)
