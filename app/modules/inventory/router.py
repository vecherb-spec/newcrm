from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.inventory.models import SKU

router = APIRouter(prefix="/inventory", tags=["Inventory"])


class SKUCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    category: str
    unit: str = "pcs"
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)


class SKURead(SKUCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    quantity_on_hand: Decimal
    quantity_reserved: Decimal


@router.get("/skus", response_model=list[SKURead])
async def list_skus(session: AsyncSession = Depends(get_session)) -> list[SKU]:
    return list(await session.scalars(select(SKU).order_by(SKU.code)))


@router.get("/alerts", response_model=list[SKURead])
async def minimum_stock_alerts(session: AsyncSession = Depends(get_session)) -> list[SKU]:
    query = select(SKU).where(SKU.quantity_on_hand - SKU.quantity_reserved <= SKU.minimum_stock)
    return list(await session.scalars(query))


@router.post("/skus", response_model=SKURead, status_code=status.HTTP_201_CREATED)
async def create_sku(payload: SKUCreate, session: AsyncSession = Depends(get_session)) -> SKU:
    sku = SKU(**payload.model_dump())
    session.add(sku)
    await session.commit()
    await session.refresh(sku)
    return sku
