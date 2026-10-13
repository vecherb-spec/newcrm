import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.models import UserRole
from app.modules.auth.router import get_current_user
from app.modules.crm.lead_specs.pricing import apply_internal_pricing


def test_markup_recalculates_selling_price_and_margin() -> None:
    specs = apply_internal_pricing(
        {
            "internal": {
                "purchase_cost_rub": 1_000_000,
                "markup_coefficient": 1.35,
            }
        },
        default_markup=Decimal("1.35"),
    )
    internal = specs["internal"]
    assert internal["screen_price_rub"] == 1_350_000.0
    assert internal["margin_rub"] == 350_000.0
    assert internal["margin_percent"] == round(350_000 / 1_350_000 * 100, 2)


def test_deal_patch_applies_default_markup_from_settings() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def session_override():
        async with sessions() as session:
            yield session

    asyncio.run(prepare())
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(),
        role=UserRole.ADMIN,
    )
    client = TestClient(app)
    try:
        pricing = client.patch(
            "/api/v1/leads/pricing-settings",
            json={"default_markup_coefficient": "1.4"},
        )
        assert pricing.status_code == 200
        lead = client.post(
            "/api/v1/leads",
            json={"title": "Наценка тест", "status": "NEW_LEAD"},
        ).json()
        updated = client.patch(
            f"/api/v1/leads/{lead['id']}",
            json={"specs": {"internal": {"purchase_cost_rub": 100000}}},
        ).json()
        internal = updated["specs"]["internal"]
        assert internal["markup_coefficient"] == 1.4
        assert float(internal["screen_price_rub"]) == 140000.0
        assert float(updated["amount"]) == 140000.0
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
