from math import ceil

from pydantic import BaseModel, Field, model_validator


class ControllerSpec(BaseModel):
    name: str = "NovaStar VX1000"
    ethernet_ports: int = Field(default=10, ge=1)
    pixels_per_port: int = Field(default=650_000, ge=1)


class UnitCosts(BaseModel):
    cabinet: float = Field(default=420.0, ge=0)
    receiving_card: float = Field(default=35.0, ge=0)
    power_supply: float = Field(default=28.0, ge=0)
    controller: float = Field(default=1_150.0, ge=0)
    signal_cable_m: float = Field(default=1.5, ge=0)
    power_cable_m: float = Field(default=2.2, ge=0)
    metal_profile_m: float = Field(default=8.0, ge=0)


class CalculationInput(BaseModel):
    width_m: float = Field(gt=0, le=100)
    height_m: float = Field(gt=0, le=50)
    pitch_mm: float = Field(gt=0.5, le=50)
    cabinet_width_mm: int = Field(default=500, gt=0)
    cabinet_height_mm: int = Field(default=500, gt=0)
    cabinet_peak_power_w: float = Field(default=160, gt=0)
    psu_capacity_w: float = Field(default=300, gt=0)
    power_redundancy_percent: float = Field(default=15, ge=0, le=100)
    brightness_nits: int = Field(default=1000, ge=400, le=12_000)
    controller: ControllerSpec = Field(default_factory=ControllerSpec)
    costs: UnitCosts = Field(default_factory=UnitCosts)
    target_margin_percent: float = Field(default=30, ge=0, lt=100)

    @model_validator(mode="after")
    def cabinet_matches_pitch(self) -> "CalculationInput":
        if self.cabinet_width_mm / self.pitch_mm < 1 or self.cabinet_height_mm / self.pitch_mm < 1:
            raise ValueError("cabinet dimensions must fit at least one pixel")
        return self


class BomLine(BaseModel):
    sku: str
    name: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float


class CalculationResult(BaseModel):
    cabinet_columns: int
    cabinet_rows: int
    cabinet_count: int
    actual_width_m: float
    actual_height_m: float
    resolution_width: int
    resolution_height: int
    total_pixels: int
    controller_count: int
    receiving_cards: int
    power_supplies: int
    peak_power_kw: float
    nominal_power_kw: float
    signal_cable_m: float
    power_cable_m: float
    metal_profile_m: float
    bom: list[BomLine]
    total_bom_cost: float
    suggested_sales_price: float
    gross_margin: float


def calculate_screen(data: CalculationInput) -> CalculationResult:
    columns = ceil(data.width_m * 1000 / data.cabinet_width_mm)
    rows = ceil(data.height_m * 1000 / data.cabinet_height_mm)
    cabinets = columns * rows
    actual_width = columns * data.cabinet_width_mm / 1000
    actual_height = rows * data.cabinet_height_mm / 1000
    resolution_width = round(actual_width * 1000 / data.pitch_mm)
    resolution_height = round(actual_height * 1000 / data.pitch_mm)
    pixels = resolution_width * resolution_height
    controller_capacity = data.controller.ethernet_ports * data.controller.pixels_per_port
    controllers = ceil(pixels / controller_capacity)
    peak_power_w = cabinets * data.cabinet_peak_power_w
    supplies = ceil(
        peak_power_w
        * (1 + data.power_redundancy_percent / 100)
        / data.psu_capacity_w
    )
    signal_cable = round(cabinets * 0.8, 1)
    power_cable = round(cabinets * 1.1, 1)
    metal_profile = round(
        2 * (actual_width + actual_height)
        + max(0, columns - 1) * actual_height
        + max(0, rows - 1) * actual_width,
        1,
    )
    quantities = [
        ("CABINET", "LED cabinets", cabinets, "pcs", data.costs.cabinet),
        ("RECEIVER", "Receiving cards", cabinets, "pcs", data.costs.receiving_card),
        ("PSU", "Power supplies", supplies, "pcs", data.costs.power_supply),
        ("CONTROLLER", data.controller.name, controllers, "pcs", data.costs.controller),
        ("SIGNAL-CABLE", "Signal cable", signal_cable, "m", data.costs.signal_cable_m),
        ("POWER-CABLE", "Power cable", power_cable, "m", data.costs.power_cable_m),
        ("METAL", "Metal profile", metal_profile, "m", data.costs.metal_profile_m),
    ]
    bom = [
        BomLine(
            sku=sku,
            name=name,
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            total_cost=round(quantity * unit_cost, 2),
        )
        for sku, name, quantity, unit, unit_cost in quantities
    ]
    total_cost = round(sum(item.total_cost for item in bom), 2)
    sales_price = round(total_cost / (1 - data.target_margin_percent / 100), 2)
    return CalculationResult(
        cabinet_columns=columns,
        cabinet_rows=rows,
        cabinet_count=cabinets,
        actual_width_m=actual_width,
        actual_height_m=actual_height,
        resolution_width=resolution_width,
        resolution_height=resolution_height,
        total_pixels=pixels,
        controller_count=controllers,
        receiving_cards=cabinets,
        power_supplies=supplies,
        peak_power_kw=round(peak_power_w / 1000, 2),
        nominal_power_kw=round(peak_power_w * 0.6 / 1000, 2),
        signal_cable_m=signal_cable,
        power_cable_m=power_cable,
        metal_profile_m=metal_profile,
        bom=bom,
        total_bom_cost=total_cost,
        suggested_sales_price=sales_price,
        gross_margin=round(sales_price - total_cost, 2),
    )
