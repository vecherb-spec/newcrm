from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.lead_specs.compute import apply_spec_computations
from app.modules.crm.lead_specs.field_catalog import (
    DEFAULT_SELECT_OPTIONS,
    SPEC_SECTIONS,
    all_field_keys,
)
from app.modules.crm.lead_specs.pricing import get_default_markup_coefficient
from app.modules.crm.models import LeadSpecFieldOptions


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_specs(
    raw: dict[str, Any] | None,
    *,
    default_markup: Decimal | None = None,
) -> dict[str, Any]:
    specs = deepcopy(raw or {})
    if "files" not in specs:
        specs["files"] = {"attachments": []}
    elif isinstance(specs.get("files"), list):
        specs["files"] = {"attachments": specs["files"]}
    markup = default_markup
    if markup is None:
        from app.modules.crm.lead_specs.pricing import DEFAULT_MARKUP

        markup = DEFAULT_MARKUP
    return apply_spec_computations(specs, default_markup=markup)


def split_specs_for_response(
    specs: dict[str, Any],
    *,
    include_internal: bool,
) -> dict[str, Any]:
    data = normalize_specs(specs)
    public = {key: value for key, value in data.items() if key != "internal"}
    if include_internal:
        public["internal"] = data.get("internal") or {}
    return public


def specs_for_documents(specs: dict[str, Any]) -> dict[str, Any]:
    """Client-safe subset for PDF/DOCX (no purchase/margin)."""
    return split_specs_for_response(specs, include_internal=False)


async def merge_lead_specs(
    session: AsyncSession,
    current: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    default_markup = await get_default_markup_coefficient(session)
    if not patch:
        return normalize_specs(current, default_markup=default_markup)
    merged = _deep_merge(current or {}, patch)
    return normalize_specs(merged, default_markup=default_markup)


def sync_lead_amount_from_specs(lead) -> None:
    internal = (lead.specs or {}).get("internal") or {}
    for key in ("total_inc_vat_rub", "screen_price_rub"):
        value = internal.get(key)
        if value is not None and value != "":
            lead.amount = Decimal(str(value))
            return


async def ensure_default_field_options(session: AsyncSession) -> None:
    for field_key, options in DEFAULT_SELECT_OPTIONS.items():
        existing = await session.get(LeadSpecFieldOptions, field_key)
        if existing is None:
            session.add(LeadSpecFieldOptions(field_key=field_key, options=options))
    await session.flush()


async def get_field_options_map(session: AsyncSession) -> dict[str, list[str]]:
    await ensure_default_field_options(session)
    rows = await session.scalars(select(LeadSpecFieldOptions))
    return {row.field_key: list(row.options) for row in rows}


def build_spec_schema(options_map: dict[str, list[str]]) -> dict[str, Any]:
    sections = []
    for section in SPEC_SECTIONS:
        fields = []
        for field in section["fields"]:
            entry = dict(field)
            options_key = entry.get("options_key")
            if options_key and options_key in options_map:
                entry["options"] = options_map[options_key]
            fields.append(entry)
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "fields": fields,
            }
        )
    return {
        "sections": sections,
        "field_keys": all_field_keys(),
    }
