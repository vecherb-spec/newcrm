import csv
import io
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.inventory.models import SKU, StockTransaction, StockTransactionType
from app.modules.inventory.service import (
    StockError,
    apply_stock_transaction,
    available_quantity,
    stock_error_to_http,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


class SKUCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    category: str
    unit: str = "pcs"
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)


class SKUUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = None
    unit: str | None = Field(default=None, max_length=20)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    minimum_stock: Decimal | None = Field(default=None, ge=0)


class SKURead(SKUCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal = Decimal("0")


class StockTransactionCreate(BaseModel):
    sku_id: UUID
    type: StockTransactionType
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    project_id: UUID | None = None
    reference: str | None = Field(default=None, max_length=255)
    note: str | None = None


class StockTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku_id: UUID
    project_id: UUID | None
    type: StockTransactionType
    quantity: Decimal
    reference: str | None
    note: str | None
    created_at: object


class ImportResult(BaseModel):
    created: int
    updated: int


def _sku_read(sku: SKU) -> SKURead:
    payload = SKURead.model_validate(sku)
    payload.quantity_available = available_quantity(sku)
    return payload


@router.get("/skus", response_model=list[SKURead])
async def list_skus(
    query: str | None = Query(default=None, min_length=1),
    category: str | None = None,
    low_stock: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[SKURead]:
    statement = select(SKU).order_by(SKU.code)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(or_(SKU.code.ilike(pattern), SKU.name.ilike(pattern)))
    if category:
        statement = statement.where(SKU.category == category)
    if low_stock:
        available = SKU.quantity_on_hand - SKU.quantity_reserved
        statement = statement.where(available <= SKU.minimum_stock)
    skus = list(await session.scalars(statement))
    return [_sku_read(sku) for sku in skus]


@router.get("/alerts", response_model=list[SKURead])
async def minimum_stock_alerts(session: AsyncSession = Depends(get_session)) -> list[SKURead]:
    return await list_skus(low_stock=True, session=session)


@router.post("/skus", response_model=SKURead, status_code=status.HTTP_201_CREATED)
async def create_sku(payload: SKUCreate, session: AsyncSession = Depends(get_session)) -> SKURead:
    sku = SKU(**payload.model_dump())
    session.add(sku)
    await session.commit()
    await session.refresh(sku)
    return _sku_read(sku)


@router.patch("/skus/{sku_id}", response_model=SKURead)
async def update_sku(
    sku_id: UUID,
    payload: SKUUpdate,
    session: AsyncSession = Depends(get_session),
) -> SKURead:
    sku = await session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sku, field, value)
    await session.commit()
    await session.refresh(sku)
    return _sku_read(sku)


@router.get("/transactions", response_model=list[StockTransactionRead])
async def list_transactions(
    sku_id: UUID | None = None,
    project_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[StockTransaction]:
    statement = select(StockTransaction).order_by(StockTransaction.created_at.desc())
    if sku_id:
        statement = statement.where(StockTransaction.sku_id == sku_id)
    if project_id:
        statement = statement.where(StockTransaction.project_id == project_id)
    return list(await session.scalars(statement))


@router.post(
    "/transactions",
    response_model=StockTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    payload: StockTransactionCreate,
    session: AsyncSession = Depends(get_session),
) -> StockTransaction:
    try:
        transaction = await apply_stock_transaction(
            session,
            sku_id=payload.sku_id,
            tx_type=payload.type,
            quantity=payload.quantity,
            project_id=payload.project_id,
            reference=payload.reference,
            note=payload.note,
        )
    except StockError as error:
        raise stock_error_to_http(error) from error
    await session.commit()
    await session.refresh(transaction)
    return transaction


@router.post("/import/csv", response_model=ImportResult)
async def import_skus_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ImportResult:
    raw = await file.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    created = 0
    updated = 0
    for row in reader:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        sku = await session.scalar(select(SKU).where(SKU.code == code))
        values = {
            "name": (row.get("name") or code).strip(),
            "category": (row.get("category") or "general").strip(),
            "unit": (row.get("unit") or "pcs").strip(),
            "unit_cost": Decimal(row.get("unit_cost") or "0"),
            "minimum_stock": Decimal(row.get("minimum_stock") or "0"),
        }
        on_hand = row.get("quantity_on_hand")
        if sku is None:
            sku = SKU(code=code, quantity_on_hand=Decimal(on_hand or "0"), **values)
            session.add(sku)
            created += 1
        else:
            for field, value in values.items():
                setattr(sku, field, value)
            if on_hand is not None:
                sku.quantity_on_hand = Decimal(on_hand)
            updated += 1
    await session.commit()
    return ImportResult(created=created, updated=updated)
