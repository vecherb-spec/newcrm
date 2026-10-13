from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.auth.router import CurrentUser
from app.modules.calculator.engine import (
    CalculationInput,
    CalculationResult,
    calculate_screen,
)
from app.modules.calculator.models import EngineeringCalculation

router = APIRouter(prefix="/calculations", tags=["Engineering"])


class SavedCalculationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    lead_id: UUID | None = None
    parameters: CalculationInput


class SavedCalculationRead(BaseModel):
    id: UUID
    name: str
    lead_id: UUID | None
    created_by_id: UUID
    parameters: CalculationInput
    result: CalculationResult
    total_bom_cost: Decimal
    suggested_sales_price: Decimal
    created_at: datetime


@router.post("/screen", response_model=CalculationResult)
async def calculate(payload: CalculationInput) -> CalculationResult:
    return calculate_screen(payload)


def _read(calculation: EngineeringCalculation) -> SavedCalculationRead:
    return SavedCalculationRead(
        id=calculation.id,
        name=calculation.name,
        lead_id=calculation.lead_id,
        created_by_id=calculation.created_by_id,
        parameters=CalculationInput.model_validate(calculation.input_data),
        result=CalculationResult.model_validate(calculation.result_data),
        total_bom_cost=calculation.total_bom_cost,
        suggested_sales_price=calculation.suggested_sales_price,
        created_at=calculation.created_at,
    )


@router.get("", response_model=list[SavedCalculationRead])
async def list_calculations(
    session: AsyncSession = Depends(get_session),
) -> list[SavedCalculationRead]:
    query = select(EngineeringCalculation).order_by(EngineeringCalculation.created_at.desc())
    calculations = await session.scalars(query.limit(50))
    return [_read(item) for item in calculations]


@router.post(
    "",
    response_model=SavedCalculationRead,
    status_code=status.HTTP_201_CREATED,
)
async def save_calculation(
    payload: SavedCalculationCreate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> SavedCalculationRead:
    result = calculate_screen(payload.parameters)
    calculation = EngineeringCalculation(
        name=payload.name,
        lead_id=payload.lead_id,
        created_by_id=user.id,
        input_data=payload.parameters.model_dump(mode="json"),
        result_data=result.model_dump(mode="json"),
        total_bom_cost=Decimal(str(result.total_bom_cost)),
        suggested_sales_price=Decimal(str(result.suggested_sales_price)),
    )
    session.add(calculation)
    await session.commit()
    await session.refresh(calculation)
    return _read(calculation)
