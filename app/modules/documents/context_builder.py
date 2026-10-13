import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.calculator.models import EngineeringCalculation
from app.modules.crm.models import Contact, Lead
from app.modules.documents.amount_words import rubles_in_words
from app.modules.documents.models import CompanyProfile, DocumentType
from app.modules.projects.models import Project


async def default_company_profile(session: AsyncSession) -> CompanyProfile:
    profile = await session.scalar(select(CompanyProfile).limit(1))
    if profile is None:
        profile = CompanyProfile(
            name='ООО «МЕДИАЛАЙВ»',
            inn="9714076643",
            kpp="771401001",
            ogrn="1217700362850",
            legal_address="127287, г. Москва, ул. 1-я Хуторская, д. 5А",
            director_name="Вечер Алена Юрьевна",
            letterhead_html="<p><strong>ООО «МЕДИАЛАЙВ»</strong> — LED экраны под ключ</p>",
        )
        session.add(profile)
        await session.flush()
    return profile


def contact_requisites(contact: Contact | None) -> dict[str, str | None]:
    if contact is None:
        return {}
    return {
        "name": contact.name,
        "company": contact.company,
        "phone": contact.phone,
        "email": contact.email,
        "inn": contact.inn,
        "kpp": contact.kpp,
        "ogrn": contact.ogrn,
        "legal_address": contact.legal_address,
        "bank_name": contact.bank_name,
        "bank_bik": contact.bank_bik,
        "bank_account": contact.bank_account,
        "bank_corr_account": contact.bank_corr_account,
    }


def company_requisites(profile: CompanyProfile) -> dict[str, str | None]:
    return {
        "name": profile.name,
        "inn": profile.inn,
        "kpp": profile.kpp,
        "ogrn": profile.ogrn,
        "legal_address": profile.legal_address,
        "bank_name": profile.bank_name,
        "bank_bik": profile.bank_bik,
        "bank_account": profile.bank_account,
        "bank_corr_account": profile.bank_corr_account,
        "director_name": profile.director_name,
    }


async def build_document_context(
    session: AsyncSession,
    *,
    doc_type: DocumentType,
    lead_id: UUID | None,
    project_id: UUID | None,
    calculation_id: UUID | None,
    amount: Decimal | None,
    vat_rate: Decimal | None,
    vat_included: bool,
    number: str,
) -> dict[str, Any]:
    profile = await default_company_profile(session)
    lead = None
    project = None
    calculation = None
    if lead_id:
        lead = await session.scalar(
            select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.contact))
        )
    if project_id:
        project = await session.get(Project, project_id)
        if project and project.lead_id and lead is None:
            lead = await session.scalar(
                select(Lead).where(Lead.id == project.lead_id).options(selectinload(Lead.contact))
            )
    if calculation_id:
        calculation = await session.get(EngineeringCalculation, calculation_id)
    elif lead:
        calculation = await session.scalar(
            select(EngineeringCalculation)
            .where(EngineeringCalculation.lead_id == lead.id)
            .order_by(EngineeringCalculation.created_at.desc())
        )

    resolved_amount = amount
    if resolved_amount is None and calculation:
        resolved_amount = calculation.suggested_sales_price
    if resolved_amount is None and lead and lead.amount:
        resolved_amount = lead.amount

    vat_value = Decimal("0")
    if resolved_amount and vat_rate:
        rate = vat_rate / Decimal("100")
        vat_value = (
            resolved_amount * rate / (Decimal("1") + rate)
            if vat_included
            else resolved_amount * rate
        )

    contact = lead.contact if lead else None
    context = {
        "doc_type": doc_type.value,
        "number": number,
        "issued_on": date.today(),
        "customer": contact_requisites(contact),
        "supplier": company_requisites(profile),
        "letterhead_html": profile.letterhead_html or "",
        "lead": {
            "id": str(lead.id) if lead else None,
            "title": lead.title if lead else None,
            "amount": str(lead.amount) if lead and lead.amount else None,
        },
        "project": {
            "id": str(project.id) if project else None,
            "name": project.name if project else None,
            "installation_address": project.installation_address if project else None,
        },
        "calculation": {
            "id": str(calculation.id) if calculation else None,
            "name": calculation.name if calculation else None,
            "parameters": calculation.input_data if calculation else {},
            "result": calculation.result_data if calculation else {},
            "total": str(calculation.suggested_sales_price) if calculation else None,
        },
        "amount": str(resolved_amount) if resolved_amount is not None else None,
        "amount_words": rubles_in_words(resolved_amount or 0),
        "vat_rate": str(vat_rate) if vat_rate is not None else None,
        "vat_included": vat_included,
        "vat_amount": str(vat_value.quantize(Decimal("0.01"))),
        "currency": "RUB",
    }
    return json.loads(json.dumps(context, default=str))
