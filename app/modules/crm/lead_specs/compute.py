from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.crm.lead_specs.pricing import DEFAULT_MARKUP, apply_internal_pricing


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


def _aspect_label(width_px: int, height_px: int) -> str:
    divisor = _gcd(width_px, height_px)
    return f"{width_px // divisor}:{height_px // divisor}"


def apply_spec_computations(
    specs: dict[str, Any],
    *,
    default_markup: Decimal = DEFAULT_MARKUP,
) -> dict[str, Any]:
    """Fill derived screen fields and internal pricing (purchase × markup)."""
    screen = dict(specs.get("screen") or {})
    width_mm = screen.get("width_mm")
    height_mm = screen.get("height_mm")
    pitch_mm = screen.get("pixel_pitch_mm")

    if width_mm and height_mm:
        try:
            w = float(width_mm)
            h = float(height_mm)
            screen["area_m2"] = round(w * h / 1_000_000, 3)
        except (TypeError, ValueError):
            pass

    if width_mm and height_mm and pitch_mm:
        try:
            w = float(width_mm)
            h = float(height_mm)
            p = float(pitch_mm)
            if p > 0:
                width_px = max(1, int(round(w / p)))
                height_px = max(1, int(round(h / p)))
                screen["resolution_px"] = f"{width_px}×{height_px}"
                screen["aspect_ratio"] = _aspect_label(width_px, height_px)
        except (TypeError, ValueError):
            pass

    if screen:
        specs["screen"] = screen
    return apply_internal_pricing(specs, default_markup=default_markup)
