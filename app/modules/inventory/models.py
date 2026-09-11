import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDTimestampMixin


class StockTransactionType(str, enum.Enum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    ADJUSTMENT = "ADJUSTMENT"
    RESERVATION = "RESERVATION"
    RELEASE = "RELEASE"


class SKU(UUIDTimestampMixin, Base):
    __tablename__ = "skus"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    quantity_reserved: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)


class StockTransaction(UUIDTimestampMixin, Base):
    __tablename__ = "stock_transactions"

    sku_id: Mapped[UUID] = mapped_column(ForeignKey("skus.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[StockTransactionType] = mapped_column(Enum(StockTransactionType))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    reference: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
