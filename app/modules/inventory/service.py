from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import SKU, StockTransaction, StockTransactionType


class StockError(ValueError):
    pass


def available_quantity(sku: SKU) -> Decimal:
    return sku.quantity_on_hand - sku.quantity_reserved


async def apply_stock_transaction(
    session: AsyncSession,
    *,
    sku_id: UUID,
    tx_type: StockTransactionType,
    quantity: Decimal,
    project_id: UUID | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> StockTransaction:
    if quantity <= 0:
        raise StockError("Количество должно быть больше нуля")
    sku = await session.get(SKU, sku_id)
    if sku is None:
        raise StockError("SKU не найден")

    if tx_type is StockTransactionType.RECEIPT:
        sku.quantity_on_hand += quantity
    elif tx_type is StockTransactionType.ISSUE:
        if available_quantity(sku) < quantity:
            raise StockError("Недостаточно доступного остатка для списания")
        sku.quantity_on_hand -= quantity
    elif tx_type is StockTransactionType.ADJUSTMENT:
        sku.quantity_on_hand += quantity
    elif tx_type is StockTransactionType.RESERVATION:
        if not project_id:
            raise StockError("Для резерва нужен проект")
        if available_quantity(sku) < quantity:
            raise StockError("Недостаточно остатка для резерва")
        sku.quantity_reserved += quantity
    elif tx_type is StockTransactionType.RELEASE:
        if not project_id:
            raise StockError("Для снятия резерва нужен проект")
        if sku.quantity_reserved < quantity:
            raise StockError("Резерв меньше запрошенного количества")
        sku.quantity_reserved -= quantity
    else:
        raise StockError("Неизвестный тип операции")

    transaction = StockTransaction(
        sku_id=sku_id,
        project_id=project_id,
        type=tx_type,
        quantity=quantity,
        reference=reference,
        note=note,
    )
    session.add(transaction)
    await session.flush()
    return transaction


def stock_error_to_http(error: StockError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


async def list_project_reservations(
    session: AsyncSession,
    project_id: UUID,
) -> list[tuple[SKU, Decimal]]:
    rows = await session.execute(
        select(SKU, StockTransaction)
        .join(StockTransaction, StockTransaction.sku_id == SKU.id)
        .where(
            StockTransaction.project_id == project_id,
            StockTransaction.type == StockTransactionType.RESERVATION,
        )
        .order_by(StockTransaction.created_at.desc())
    )
    totals: dict[UUID, tuple[SKU, Decimal]] = {}
    for sku, transaction in rows:
        current = totals.get(sku.id, (sku, Decimal("0")))[1]
        totals[sku.id] = (sku, current + transaction.quantity)
    return list(totals.values())
