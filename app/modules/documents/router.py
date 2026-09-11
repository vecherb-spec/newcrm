from datetime import date
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.calculator.models import EngineeringCalculation
from app.modules.crm.models import Lead
from app.modules.documents.service import render_document, render_pdf
from app.modules.finance.models import Invoice
from app.modules.projects.models import Project

router = APIRouter(prefix="/documents", tags=["Documents"])


def _pdf_response(content: bytes, filename: str) -> Response:
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


async def _quote_context(
    calculation_id: UUID,
    session: AsyncSession,
) -> dict[str, object]:
    calculation = await session.get(EngineeringCalculation, calculation_id)
    if calculation is None:
        raise HTTPException(status_code=404, detail="Calculation not found")
    lead = await session.get(Lead, calculation.lead_id) if calculation.lead_id else None
    parsed = lead.parsed_data if lead else {}
    customer = (
        parsed.get("contact_name")
        or parsed.get("company")
        or (lead.title if lead else None)
        or "Заказчик"
    )
    return {
        "number": f"KP-{str(calculation.id)[:8].upper()}",
        "customer": customer,
        "project": calculation.name,
        "parameters": calculation.input_data,
        "result": calculation.result_data,
        "total": calculation.suggested_sales_price,
        "currency": "RUB",
        "issued_on": date.today(),
    }


@router.get("/quotes/{calculation_id}/preview", response_class=HTMLResponse)
async def preview_quote(
    calculation_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> str:
    context = await _quote_context(calculation_id, session)
    return render_document("quote.html", context)


@router.get("/quotes/{calculation_id}.pdf")
async def quote_pdf(
    calculation_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    context = await _quote_context(calculation_id, session)
    return _pdf_response(
        render_pdf("quote.html", context),
        f"quote-{calculation_id}.pdf",
    )


@router.get("/invoices/{invoice_id}.pdf")
async def invoice_pdf(
    invoice_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    project = await session.get(Project, invoice.project_id)
    context = {
        "invoice": invoice,
        "project": project,
        "issued_on": invoice.created_at.date(),
        "currency": "RUB",
    }
    return _pdf_response(
        render_pdf("invoice.html", context),
        f"invoice-{invoice.number}.pdf",
    )


@router.get("/acts/{project_id}.pdf")
async def acceptance_act_pdf(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    project = await session.scalar(
        select(Project).where(Project.id == project_id).options(selectinload(Project.tasks))
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    context = {
        "number": f"ACT-{str(project.id)[:8].upper()}",
        "project": project,
        "issued_on": date.today(),
    }
    return _pdf_response(
        render_pdf("act.html", context),
        f"act-{project_id}.pdf",
    )
