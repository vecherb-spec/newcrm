import pytest

from app.modules.calculator.engine import CalculationInput, calculate_screen


def test_calculates_layout_power_and_margin() -> None:
    result = calculate_screen(
        CalculationInput(
            width_m=3.2,
            height_m=1.8,
            pitch_mm=2.5,
            cabinet_width_mm=500,
            cabinet_height_mm=500,
            target_margin_percent=20,
        )
    )

    assert (result.cabinet_columns, result.cabinet_rows) == (7, 4)
    assert result.cabinet_count == 28
    assert result.resolution_width == 1400
    assert result.resolution_height == 800
    assert result.power_supplies == 18
    assert result.suggested_sales_price > result.total_bom_cost
    assert result.gross_margin == pytest.approx(result.suggested_sales_price * 0.2, abs=0.01)


def test_rounds_requested_dimensions_up_to_whole_cabinets() -> None:
    result = calculate_screen(CalculationInput(width_m=1.01, height_m=1.01, pitch_mm=2.5))

    assert result.actual_width_m == 1.5
    assert result.actual_height_m == 1.5
