from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.finance.models import EntryType, FinanceEntry, Invoice
from app.modules.projects.models import Project

router = APIRouter(prefix="/finance", tags=["Finance"])


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    CANCELLED = "cancelled"


class FinanceEntryCreate(BaseModel):
    type: EntryType
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    is_planned: bool = False
    occurred_on: date | None = None
    description: str | None = Field(default=None, max_length=255)


class FinanceEntryRead(FinanceEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime


class InvoiceCreate(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date | None = None


class InvoiceRead(InvoiceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: InvoiceStatus
    created_at: datetime


class InvoiceUpdate(BaseModel):
    status: InvoiceStatus


class ProjectEconomics(BaseModel):
    project_id: UUID
    planned_revenue: Decimal
    actual_revenue: Decimal
    planned_costs: Decimal
    actual_costs: Decimal
    gross_margin: Decimal
    gross_margin_percent: Decimal | None
    actual_costs_by_type: dict[EntryType, Decimal]


async def _require_project(project_id: UUID, session: AsyncSession) -> None:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/{project_id}/economics", response_model=ProjectEconomics)
async def project_economics(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> ProjectEconomics:
    await _require_project(project_id, session)
    entries = list(
        await session.scalars(
            select(FinanceEntry).where(FinanceEntry.project_id == project_id)
        )
    )
    zero = Decimal("0")
    planned_revenue = sum(
        (item.amount for item in entries if item.is_planned and item.type is EntryType.REVENUE),
        zero,
    )
    actual_revenue = sum(
        (
            item.amount
            for item in entries
            if not item.is_planned and item.type is EntryType.REVENUE
        ),
        zero,
    )
    planned_costs = sum(
        (item.amount for item in entries if item.is_planned and item.type is not EntryType.REVENUE),
        zero,
    )
    actual_costs_by_type = {
        entry_type: sum(
            (
                item.amount
                for item in entries
                if not item.is_planned and item.type is entry_type
            ),
            zero,
        )
        for entry_type in EntryType
        if entry_type is not EntryType.REVENUE
    }
    actual_costs = sum(actual_costs_by_type.values(), zero)
    gross_margin = actual_revenue - actual_costs
    margin_percent = (
        (gross_margin / actual_revenue * 100).quantize(Decimal("0.01"))
        if actual_revenue
        else None
    )
    return ProjectEconomics(
        project_id=project_id,
        planned_revenue=planned_revenue,
        actual_revenue=actual_revenue,
        planned_costs=planned_costs,
        actual_costs=actual_costs,
        gross_margin=gross_margin,
        gross_margin_percent=margin_percent,
        actual_costs_by_type=actual_costs_by_type,
    )


@router.get(
    "/projects/{project_id}/entries",
    response_model=list[FinanceEntryRead],
)
async def list_entries(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[FinanceEntry]:
    await _require_project(project_id, session)
    query = (
        select(FinanceEntry)
        .where(FinanceEntry.project_id == project_id)
        .order_by(FinanceEntry.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post(
    "/projects/{project_id}/entries",
    response_model=FinanceEntryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_entry(
    project_id: UUID,
    payload: FinanceEntryCreate,
    session: AsyncSession = Depends(get_session),
) -> FinanceEntry:
    await _require_project(project_id, session)
    entry = FinanceEntry(project_id=project_id, **payload.model_dump())
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.get(
    "/projects/{project_id}/invoices",
    response_model=list[InvoiceRead],
)
async def list_invoices(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[Invoice]:
    await _require_project(project_id, session)
    query = (
        select(Invoice)
        .where(Invoice.project_id == project_id)
        .order_by(Invoice.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post(
    "/projects/{project_id}/invoices",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    project_id: UUID,
    payload: InvoiceCreate,
    session: AsyncSession = Depends(get_session),
) -> Invoice:
    await _require_project(project_id, session)
    invoice = Invoice(
        project_id=project_id,
        status=InvoiceStatus.DRAFT.value,
        **payload.model_dump(),
    )
    session.add(invoice)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Invoice number already exists") from error
    await session.refresh(invoice)
    return invoice


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(
    invoice_id: UUID,
    payload: InvoiceUpdate,
    session: AsyncSession = Depends(get_session),
) -> Invoice:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = payload.status.value
    await session.commit()
    await session.refresh(invoice)
    return invoice
