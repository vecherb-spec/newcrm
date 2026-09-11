from fastapi import APIRouter

from app.modules.calculator.engine import (
    CalculationInput,
    CalculationResult,
    calculate_screen,
)

router = APIRouter(prefix="/calculations", tags=["Engineering"])


@router.post("/screen", response_model=CalculationResult)
async def calculate(payload: CalculationInput) -> CalculationResult:
    return calculate_screen(payload)
