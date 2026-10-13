import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.router import get_current_user


def _client() -> tuple[TestClient, object]:
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
        role="ADMIN",
    )
    return TestClient(app), engine


def test_pipeline_stages_seeded_in_amo_order() -> None:
    client, engine = _client()
    try:
        stages = client.get("/api/v1/leads/stages")
        assert stages.status_code == 200
        data = stages.json()
        assert len(data) == 13
        assert data[0]["code"] == "UNSORTED"
        assert data[0]["amo_status_id"] == 88792562
        assert data[1]["code"] == "NEW_LEAD"
        assert data[-2]["code"] == "CLOSED_WON"
        assert data[-2]["amo_status_id"] == 142
        assert data[-1]["code"] == "CLOSED_LOST"
        assert data[-1]["amo_status_id"] == 143
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_amo_import_maps_status_id() -> None:
    client, engine = _client()
    try:
        payload = [
            {
                "amo_id": "amo-stage-id",
                "title": "Сделка по amo status",
                "amo_status_id": 88792854,
                "contact": {"name": "Тест", "phone": "+79990001122"},
            }
        ]
        response = client.post("/api/v1/imports/amo/deals", json=payload)
        assert response.status_code == 200
        lead = client.get("/api/v1/leads/lookup?amo_id=amo-stage-id").json()[0]
        assert lead["status"] == "PROPOSAL_SENT"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_calculation_stage_migrates_to_qualification_alias() -> None:
    client, engine = _client()
    try:
        payload = [
            {
                "amo_id": "amo-calc",
                "title": "Старый расчёт",
                "stage": "CALCULATION",
                "contact": {"name": "Тест"},
            }
        ]
        response = client.post("/api/v1/imports/amo/deals", json=payload)
        assert response.status_code == 200
        lead = client.get("/api/v1/leads/lookup?amo_id=amo-calc").json()[0]
        assert lead["status"] == "QUALIFICATION"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
