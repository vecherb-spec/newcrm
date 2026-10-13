from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import CrmPricingSettings

DEFAULT_MARKUP = Decimal("1.35")
SETTINGS_ROW_ID = 1


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apply_internal_pricing(
    specs: dict[str, Any],
    *,
    default_markup: Decimal = DEFAULT_MARKUP,
) -> dict[str, Any]:
    internal = dict(specs.get("internal") or {})
    purchase = _to_decimal(internal.get("purchase_cost_rub"))
    markup = _to_decimal(internal.get("markup_coefficient"))
    if markup is None:
        markup = default_markup
        internal["markup_coefficient"] = _money(markup)

    if purchase is not None and markup is not None and purchase >= 0 and markup > 0:
        screen_price = (purchase * markup).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        margin = screen_price - purchase
        internal["screen_price_rub"] = _money(screen_price)
        internal["margin_rub"] = _money(margin)
        if screen_price > 0:
            margin_pct = (margin / screen_price * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            internal["margin_percent"] = float(margin_pct)

        extras = Decimal("0")
        for key in (
            "frame_price_rub",
            "installation_price_rub",
            "delivery_price_rub",
            "controller_price_rub",
        ):
            extra = _to_decimal(internal.get(key))
            if extra is not None:
                extras += extra
        subtotal = screen_price + extras
        internal["subtotal_ex_vat_rub"] = _money(subtotal)
        vat_percent = _to_decimal(internal.get("vat_percent"))
        if vat_percent is not None and vat_percent > 0:
            vat_amount = (subtotal * vat_percent / Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            internal["vat_amount_rub"] = _money(vat_amount)
            internal["total_inc_vat_rub"] = _money(subtotal + vat_amount)

    specs["internal"] = internal
    return specs


async def get_default_markup_coefficient(session: AsyncSession) -> Decimal:
    row = await session.get(CrmPricingSettings, SETTINGS_ROW_ID)
    if row is None:
        row = CrmPricingSettings(id=SETTINGS_ROW_ID, default_markup_coefficient=DEFAULT_MARKUP)
        session.add(row)
        await session.flush()
    return row.default_markup_coefficient


async def set_default_markup_coefficient(
    session: AsyncSession,
    value: Decimal,
) -> Decimal:
    row = await session.get(CrmPricingSettings, SETTINGS_ROW_ID)
    if row is None:
        row = CrmPricingSettings(id=SETTINGS_ROW_ID, default_markup_coefficient=value)
        session.add(row)
    else:
        row.default_markup_coefficient = value
    await session.flush()
    return row.default_markup_coefficient
