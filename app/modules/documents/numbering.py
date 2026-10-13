from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import DocumentNumberSequence, DocumentType

PREFIX = {
    DocumentType.SUPPLY_CONTRACT: "ДП",
    DocumentType.INVOICE: "СЧ",
    DocumentType.WAYBILL_UPD: "УПД",
    DocumentType.ACT: "АКТ",
    DocumentType.QUOTE: "КП",
    DocumentType.SPECIFICATION: "СП",
}


async def allocate_document_number(
    session: AsyncSession,
    doc_type: DocumentType,
) -> tuple[str, int]:
    year = datetime.now(UTC).year
    row = await session.scalar(
        select(DocumentNumberSequence).where(
            DocumentNumberSequence.doc_type == doc_type,
            DocumentNumberSequence.year == year,
        )
    )
    if row is None:
        row = DocumentNumberSequence(doc_type=doc_type, year=year, last_number=0)
        session.add(row)
        await session.flush()
    row.last_number += 1
    prefix = PREFIX[doc_type]
    number = f"{prefix}-{year}-{row.last_number:04d}"
    return number, year
