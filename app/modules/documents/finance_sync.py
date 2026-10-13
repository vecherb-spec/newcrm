from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import DocumentStatus, DocumentType, GeneratedDocument
from app.modules.finance.models import EntryType, FinanceEntry, Invoice


async def sync_invoice_paid_status(
    session: AsyncSession,
    document: GeneratedDocument,
) -> None:
    if document.doc_type is not DocumentType.INVOICE:
        return
    if document.status is not DocumentStatus.PAID or document.paid_at is not None:
        return
    if not document.project_id or document.amount is None:
        return

    invoice = None
    if document.finance_invoice_id:
        invoice = await session.get(Invoice, document.finance_invoice_id)
    if invoice is None:
        invoice = Invoice(
            project_id=document.project_id,
            number=document.number,
            amount=document.amount,
            status="paid",
            due_date=date.today(),
        )
        session.add(invoice)
        await session.flush()
        document.finance_invoice_id = invoice.id
    else:
        invoice.status = "paid"

    entry = FinanceEntry(
        project_id=document.project_id,
        type=EntryType.REVENUE,
        amount=Decimal(document.amount),
        is_planned=False,
        occurred_on=date.today(),
        description=f"Оплата по счёту {document.number}",
    )
    session.add(entry)
    document.paid_at = datetime.now(UTC)
