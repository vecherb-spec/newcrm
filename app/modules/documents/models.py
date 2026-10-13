from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDTimestampMixin


class DocumentType(StrEnum):
    SUPPLY_CONTRACT = "SUPPLY_CONTRACT"
    INVOICE = "INVOICE"
    WAYBILL_UPD = "WAYBILL_UPD"
    ACT = "ACT"
    QUOTE = "QUOTE"
    SPECIFICATION = "SPECIFICATION"


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    SIGNED = "SIGNED"
    PAID = "PAID"


class CompanyProfile(UUIDTimestampMixin, Base):
    __tablename__ = "company_profile"

    name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str] = mapped_column(String(12))
    kpp: Mapped[str | None] = mapped_column(String(9))
    ogrn: Mapped[str | None] = mapped_column(String(15))
    legal_address: Mapped[str | None] = mapped_column(Text)
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_bik: Mapped[str | None] = mapped_column(String(9))
    bank_account: Mapped[str | None] = mapped_column(String(34))
    bank_corr_account: Mapped[str | None] = mapped_column(String(34))
    director_name: Mapped[str | None] = mapped_column(String(160))
    letterhead_html: Mapped[str | None] = mapped_column(Text)


class DocumentTemplate(UUIDTimestampMixin, Base):
    __tablename__ = "document_templates"

    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), index=True)
    name: Mapped[str] = mapped_column(String(160))
    body_html: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class DocumentNumberSequence(Base):
    __tablename__ = "document_number_sequences"

    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class GeneratedDocument(UUIDTimestampMixin, Base):
    __tablename__ = "generated_documents"

    root_id: Mapped[UUID | None] = mapped_column(ForeignKey("generated_documents.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DRAFT, index=True
    )
    number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    number_year: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    calculation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("engineering_calculations.id")
    )
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_templates.id"))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    vat_included: Mapped[bool] = mapped_column(Boolean, default=True)
    context_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rendered_html: Mapped[str | None] = mapped_column(Text)
    scan_storage_key: Mapped[str | None] = mapped_column(String(255))
    finance_invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
