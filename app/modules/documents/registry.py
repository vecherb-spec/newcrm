from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.modules.documents.context_builder import default_company_profile
from app.modules.documents.defaults import ensure_default_templates
from app.modules.documents.finance_sync import sync_invoice_paid_status
from app.modules.documents.generator import (
    generate_document,
    html_to_docx_bytes,
    store_scan_bytes,
)
from app.modules.documents.models import (
    CompanyProfile,
    DocumentStatus,
    DocumentTemplate,
    DocumentType,
    GeneratedDocument,
)
from app.modules.documents.service import render_pdf_html


def _attachment_disposition(filename: str) -> dict[str, str]:
    ascii_name = "".join(
        char if ord(char) < 128 and char not in {'"', "\\"} else "_" for char in filename
    )
    if not ascii_name.strip():
        ascii_name = "document"
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'
        ),
    }


router = APIRouter(tags=["Documents"])


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doc_type: DocumentType
    name: str
    body_html: str
    is_active: bool
    version: int


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    body_html: str | None = None
    is_active: bool | None = None


class CompanyProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    inn: str
    kpp: str | None
    ogrn: str | None
    legal_address: str | None
    bank_name: str | None
    bank_bik: str | None
    bank_account: str | None
    bank_corr_account: str | None
    director_name: str | None
    letterhead_html: str | None


class CompanyProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    ogrn: str | None = Field(default=None, max_length=15)
    legal_address: str | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=9)
    bank_account: str | None = Field(default=None, max_length=34)
    bank_corr_account: str | None = Field(default=None, max_length=34)
    director_name: str | None = Field(default=None, max_length=160)
    letterhead_html: str | None = None


class GenerateDocumentRequest(BaseModel):
    doc_type: DocumentType
    title: str = Field(min_length=2, max_length=255)
    lead_id: UUID | None = None
    project_id: UUID | None = None
    calculation_id: UUID | None = None
    template_id: UUID | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    vat_rate: Decimal | None = Field(default=Decimal("20"), ge=0, le=100, decimal_places=2)
    vat_included: bool = True


class DocumentStatusUpdate(BaseModel):
    status: DocumentStatus


class GeneratedDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    root_id: UUID | None
    version: int
    is_current: bool
    doc_type: DocumentType
    status: DocumentStatus
    number: str
    number_year: int
    title: str
    lead_id: UUID | None
    project_id: UUID | None
    calculation_id: UUID | None
    amount: Decimal | None
    vat_rate: Decimal | None
    vat_included: bool
    scan_storage_key: str | None
    finance_invoice_id: UUID | None


async def _active_template(
    session: AsyncSession,
    doc_type: DocumentType,
    template_id: UUID | None,
) -> DocumentTemplate:
    if template_id:
        template = await session.get(DocumentTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Шаблон не найден")
        return template
    template = await session.scalar(
        select(DocumentTemplate)
        .where(DocumentTemplate.doc_type == doc_type, DocumentTemplate.is_active.is_(True))
        .order_by(DocumentTemplate.version.desc())
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Активный шаблон не найден")
    return template


@router.get("/company-profile", response_model=CompanyProfileRead)
async def get_company_profile(session: AsyncSession = Depends(get_session)) -> CompanyProfile:
    await ensure_default_templates(session)
    return await default_company_profile(session)


@router.patch("/company-profile", response_model=CompanyProfileRead)
async def update_company_profile(
    payload: CompanyProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> CompanyProfile:
    profile = await default_company_profile(session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/templates", response_model=list[TemplateRead])
async def list_templates(session: AsyncSession = Depends(get_session)) -> list[DocumentTemplate]:
    await ensure_default_templates(session)
    return list(await session.scalars(select(DocumentTemplate).order_by(DocumentTemplate.doc_type)))


@router.patch("/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
) -> DocumentTemplate:
    template = await session.get(DocumentTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    data = payload.model_dump(exclude_unset=True)
    if data:
        template.version += 1
        for field, value in data.items():
            setattr(template, field, value)
    await session.commit()
    await session.refresh(template)
    return template


@router.get("/documents", response_model=list[GeneratedDocumentRead])
async def list_documents(
    query: str | None = Query(default=None, min_length=1),
    lead_id: UUID | None = None,
    project_id: UUID | None = None,
    doc_type: DocumentType | None = None,
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[GeneratedDocument]:
    await ensure_default_templates(session)
    statement = select(GeneratedDocument).where(GeneratedDocument.is_current.is_(True))
    if lead_id:
        statement = statement.where(GeneratedDocument.lead_id == lead_id)
    if project_id:
        statement = statement.where(GeneratedDocument.project_id == project_id)
    if doc_type:
        statement = statement.where(GeneratedDocument.doc_type == doc_type)
    if status_filter:
        statement = statement.where(GeneratedDocument.status == status_filter)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                GeneratedDocument.number.ilike(pattern),
                GeneratedDocument.title.ilike(pattern),
            )
        )
    statement = statement.order_by(GeneratedDocument.created_at.desc())
    return list(await session.scalars(statement))


@router.post(
    "/documents/generate",
    response_model=GeneratedDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_document_endpoint(
    payload: GenerateDocumentRequest,
    session: AsyncSession = Depends(get_session),
) -> GeneratedDocument:
    await ensure_default_templates(session)
    template = await _active_template(session, payload.doc_type, payload.template_id)
    document = await generate_document(
        session,
        doc_type=payload.doc_type,
        title=payload.title,
        template=template,
        lead_id=payload.lead_id,
        project_id=payload.project_id,
        calculation_id=payload.calculation_id,
        amount=payload.amount,
        vat_rate=payload.vat_rate,
        vat_included=payload.vat_included,
    )
    await session.commit()
    await session.refresh(document)
    return document


@router.get("/documents/{document_id}", response_model=GeneratedDocumentRead)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> GeneratedDocument:
    document = await session.get(GeneratedDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return document


@router.patch("/documents/{document_id}/status", response_model=GeneratedDocumentRead)
async def update_document_status(
    document_id: UUID,
    payload: DocumentStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> GeneratedDocument:
    document = await session.get(GeneratedDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    document.status = payload.status
    now = datetime.now(UTC)
    if payload.status is DocumentStatus.SENT:
        document.sent_at = now
    if payload.status is DocumentStatus.SIGNED:
        document.signed_at = now
    if payload.status is DocumentStatus.PAID:
        await sync_invoice_paid_status(session, document)
    await session.commit()
    await session.refresh(document)
    return document


@router.post("/documents/{document_id}/revise", response_model=GeneratedDocumentRead)
async def revise_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> GeneratedDocument:
    current = await session.get(GeneratedDocument, document_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    current.is_current = False
    revision = GeneratedDocument(
        root_id=current.root_id or current.id,
        version=current.version + 1,
        is_current=True,
        doc_type=current.doc_type,
        status=DocumentStatus.DRAFT,
        number=current.number,
        number_year=current.number_year,
        title=current.title,
        lead_id=current.lead_id,
        project_id=current.project_id,
        calculation_id=current.calculation_id,
        template_id=current.template_id,
        amount=current.amount,
        vat_rate=current.vat_rate,
        vat_included=current.vat_included,
        context_data=current.context_data,
        rendered_html=current.rendered_html,
    )
    session.add(revision)
    await session.commit()
    await session.refresh(revision)
    return revision


@router.get("/documents/{document_id}/preview", response_class=HTMLResponse)
async def preview_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> str:
    document = await session.get(GeneratedDocument, document_id)
    if document is None or not document.rendered_html:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return document.rendered_html


@router.get("/documents/{document_id}/pdf")
async def download_document_pdf(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await session.get(GeneratedDocument, document_id)
    if document is None or not document.rendered_html:
        raise HTTPException(status_code=404, detail="Документ не найден")
    pdf = render_pdf_html(document.rendered_html)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers=_attachment_disposition(f"{document.number}.pdf"),
    )


@router.get("/documents/{document_id}/docx")
async def download_document_docx(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await session.get(GeneratedDocument, document_id)
    if document is None or not document.rendered_html:
        raise HTTPException(status_code=404, detail="Документ не найден")
    content = html_to_docx_bytes(document.rendered_html)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_disposition(f"{document.number}.docx"),
    )


@router.post("/documents/{document_id}/scan", response_model=GeneratedDocumentRead)
async def upload_signed_scan(
    document_id: UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> GeneratedDocument:
    document = await session.get(GeneratedDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    payload = await file.read()
    storage_root = Path(get_settings().document_storage_dir)
    document.scan_storage_key = store_scan_bytes(
        storage_root,
        document.id,
        file.filename or "scan.pdf",
        payload,
    )
    document.status = DocumentStatus.SIGNED
    document.signed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(document)
    return document

