import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDTimestampMixin


class EntryType(str, enum.Enum):
    REVENUE = "REVENUE"
    MATERIAL = "MATERIAL"
    PAYROLL = "PAYROLL"
    DELIVERY = "DELIVERY"
    TRAVEL = "TRAVEL"
    RENTAL = "RENTAL"
    OTHER = "OTHER"


class FinanceEntry(UUIDTimestampMixin, Base):
    __tablename__ = "finance_entries"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[EntryType] = mapped_column(Enum(EntryType))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    is_planned: Mapped[bool] = mapped_column(default=False)
    occurred_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(255))


class Invoice(UUIDTimestampMixin, Base):
    __tablename__ = "invoices"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[str] = mapped_column(String(80), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    due_date: Mapped[date | None] = mapped_column(Date)
