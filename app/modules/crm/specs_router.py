from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.modules.auth.models import User, UserRole
from app.modules.auth.router import CurrentUser
from app.modules.crm.lead_specs.pricing import (
    get_default_markup_coefficient,
    set_default_markup_coefficient,
)
from app.modules.crm.lead_specs.service import (
    build_spec_schema,
    get_field_options_map,
    merge_lead_specs,
    sync_lead_amount_from_specs,
)
from app.modules.crm.lead_specs.timeline import build_lead_timeline
from app.modules.crm.models import Lead, LeadSpecFieldOptions


async def _require_lead(lead_id: UUID, session: AsyncSession) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    return lead

router = APIRouter(tags=["CRM"])


class SpecOptionsUpdate(BaseModel):
    options: list[str] = Field(min_length=1)


class PricingSettingsRead(BaseModel):
    default_markup_coefficient: Decimal


class PricingSettingsUpdate(BaseModel):
    default_markup_coefficient: Decimal = Field(gt=0, max_digits=8, decimal_places=4)


async def _require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор")
    return user


def _include_internal(user: User | None) -> bool:
    return user is not None


@router.get("/leads/pricing-settings", response_model=PricingSettingsRead)
async def read_pricing_settings(
    session: AsyncSession = Depends(get_session),
) -> PricingSettingsRead:
    value = await get_default_markup_coefficient(session)
    return PricingSettingsRead(default_markup_coefficient=value)


@router.patch("/leads/pricing-settings", response_model=PricingSettingsRead)
async def update_pricing_settings(
    payload: PricingSettingsUpdate,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> PricingSettingsRead:
    value = await set_default_markup_coefficient(session, payload.default_markup_coefficient)
    await session.commit()
    return PricingSettingsRead(default_markup_coefficient=value)


@router.get(
    "/leads/spec-schema",
    summary="Схема полей карточки сделки LED",
    description="Секции, типы, единицы и списки выбора для бота Малыш и UI.",
)
async def get_lead_spec_schema(session: AsyncSession = Depends(get_session)) -> dict:
    options_map = await get_field_options_map(session)
    return build_spec_schema(options_map)


@router.patch("/leads/spec-options/{field_key}", response_model=dict)
async def update_spec_field_options(
    field_key: str,
    payload: SpecOptionsUpdate,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(LeadSpecFieldOptions, field_key)
    if row is None:
        row = LeadSpecFieldOptions(field_key=field_key, options=payload.options)
        session.add(row)
    else:
        row.options = payload.options
    await session.commit()
    return {"field_key": field_key, "options": row.options}


@router.get(
    "/leads/{lead_id}/timeline",
    summary="Единая лента карточки сделки",
)
async def get_lead_timeline(
    lead_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _require_lead(lead_id, session)
    return await build_lead_timeline(session, lead_id)


@router.post("/leads/{lead_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_lead_file(
    lead_id: UUID,
    file: UploadFile = File(...),
    kind: str = "other",
    session: AsyncSession = Depends(get_session),
) -> dict:
    lead = await _require_lead(lead_id, session)
    settings = get_settings()
    storage = Path(settings.document_storage_dir) / "lead_files" / str(lead_id)
    storage.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.bin").suffix
    stored_name = f"{uuid4()}{suffix}"
    target = storage / stored_name
    content = await file.read()
    target.write_bytes(content)

    entry = {
        "id": str(uuid4()),
        "kind": kind,
        "name": file.filename or stored_name,
        "path": str(target.relative_to(settings.document_storage_dir)),
        "mime": file.content_type,
    }
    specs = dict(lead.specs or {})
    files_section = dict(specs.get("files") or {})
    attachments = list(files_section.get("attachments") or [])
    attachments.append(entry)
    files_section["attachments"] = attachments
    specs["files"] = files_section
    lead.specs = await merge_lead_specs(session, lead.specs, specs)
    sync_lead_amount_from_specs(lead)
    await session.commit()
    return entry
