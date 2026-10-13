from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDTimestampMixin


class EngineeringCalculation(UUIDTimestampMixin, Base):
    __tablename__ = "engineering_calculations"

    name: Mapped[str] = mapped_column(String(255))
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    total_bom_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    suggested_sales_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
