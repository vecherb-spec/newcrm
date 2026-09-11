from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.finance.models import EntryType, FinanceEntry

router = APIRouter(prefix="/finance", tags=["Finance"])


class ProjectEconomics(BaseModel):
    project_id: UUID
    planned_revenue: Decimal
    actual_revenue: Decimal
    actual_costs: Decimal
    gross_margin: Decimal


@router.get("/projects/{project_id}/economics", response_model=ProjectEconomics)
async def project_economics(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> ProjectEconomics:
    revenue = case((FinanceEntry.type == EntryType.REVENUE, FinanceEntry.amount), else_=0)
    costs = case((FinanceEntry.type != EntryType.REVENUE, FinanceEntry.amount), else_=0)
    row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(case((FinanceEntry.is_planned.is_(True), revenue), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((FinanceEntry.is_planned.is_(False), revenue), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((FinanceEntry.is_planned.is_(False), costs), else_=0)), 0
                ),
            ).where(FinanceEntry.project_id == project_id)
        )
    ).one()
    planned_revenue, actual_revenue, actual_costs = map(Decimal, row)
    return ProjectEconomics(
        project_id=project_id,
        planned_revenue=planned_revenue,
        actual_revenue=actual_revenue,
        actual_costs=actual_costs,
        gross_margin=actual_revenue - actual_costs,
    )
