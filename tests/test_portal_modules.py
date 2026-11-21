import asyncio
import io
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
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    return TestClient(app), engine


def test_inventory_transactions_and_csv_import() -> None:
    client, engine = _client()
    try:
        sku = client.post(
            "/api/v1/inventory/skus",
            json={
                "code": "MOD-500",
                "name": "Модуль 500x500",
                "category": "module",
                "unit_cost": "12000",
                "minimum_stock": "2",
            },
        )
        assert sku.status_code == 201
        sku_id = sku.json()["id"]

        receipt = client.post(
            "/api/v1/inventory/transactions",
            json={"sku_id": sku_id, "type": "RECEIPT", "quantity": "10"},
        )
        assert receipt.status_code == 201

        project = client.post("/api/v1/projects", json={"name": "Проект склада"}).json()
        reserve = client.post(
            "/api/v1/inventory/transactions",
            json={
                "sku_id": sku_id,
                "type": "RESERVATION",
                "quantity": "3",
                "project_id": project["id"],
            },
        )
        assert reserve.status_code == 201

        listed = client.get("/api/v1/inventory/skus?query=MOD")
        assert listed.status_code == 200
        item = listed.json()[0]
        assert item["quantity_on_hand"] == "10.000"
        assert item["quantity_reserved"] == "3.000"
        assert item["quantity_available"] == "7.000"

        csv_body = (
            "code,name,category,unit,unit_cost,quantity_on_hand,minimum_stock\n"
            "PSU-350,Блок питания 350W,psu,pcs,4500,5,1\n"
        )
        imported = client.post(
            "/api/v1/inventory/import/csv",
            files={"file": ("stock.csv", io.BytesIO(csv_body.encode()), "text/csv")},
        )
        assert imported.status_code == 200
        assert imported.json()["created"] == 1

        alerts = client.get("/api/v1/inventory/alerts")
        assert alerts.status_code == 200
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_installation_conflicts_and_calendar() -> None:
    client, engine = _client()
    try:
        project = client.post("/api/v1/projects", json={"name": "Монтаж ТЦ"}).json()
        crew = client.post(
            "/api/v1/installations/crew",
            json={"name": "Иван Монтажник", "phone": "+79990000001", "role": "INSTALLER"},
        ).json()

        first = client.post(
            "/api/v1/installations/jobs",
            json={
                "project_id": project["id"],
                "title": "Монтаж утром",
                "address": "Москва",
                "starts_at": "2026-10-20T09:00:00+00:00",
                "ends_at": "2026-10-20T13:00:00+00:00",
                "crew_member_ids": [crew["id"]],
            },
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/installations/jobs",
            json={
                "project_id": project["id"],
                "title": "Монтаж днем",
                "address": "Москва",
                "starts_at": "2026-10-20T12:00:00+00:00",
                "ends_at": "2026-10-20T16:00:00+00:00",
                "crew_member_ids": [crew["id"]],
            },
        )
        assert second.status_code == 201
        assert second.json()["conflicts"]

        calendar = client.get(
            "/api/v1/installations/calendar"
            "?start=2026-10-20T00:00:00%2B00:00&end=2026-10-21T00:00:00%2B00:00"
        )
        assert calendar.status_code == 200
        assert len(calendar.json()) == 2
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_project_auto_create_on_prepayment_stage() -> None:
    client, engine = _client()
    try:
        lead = client.post(
            "/api/v1/leads",
            json={
                "title": "Экран в офис",
                "status": "PREPAYMENT",
                "amount": "500000",
                "contract_signed": True,
                "paid": True,
                "specs": {"screen": {"install_address": "Москва, ул. Тестовая 1"}},
            },
        )
        assert lead.status_code == 201
        lead_id = lead.json()["id"]

        project = client.get(f"/api/v1/projects/by-lead/{lead_id}")
        assert project.status_code == 200
        assert project.json() is not None
        assert project.json()["amount"] == "500000.00"
        assert project.json()["status"] == "PLANNING"
        assert project.json()["installation_address"] == "Москва, ул. Тестовая 1"

        detail = client.get(f"/api/v1/projects/{project.json()['id']}")
        assert detail.status_code == 200
        assert detail.json()["economics"] is not None
        assert detail.json()["specs"]["screen"]["install_address"] == "Москва, ул. Тестовая 1"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_project_manual_create_without_closed_won() -> None:
    client, engine = _client()
    try:
        lead = client.post(
            "/api/v1/leads",
            json={
                "title": "Ручной проект",
                "status": "NEGOTIATION",
                "contract_signed": True,
                "paid": True,
            },
        )
        assert lead.status_code == 201
        lead_id = lead.json()["id"]

        empty = client.get(f"/api/v1/projects/by-lead/{lead_id}")
        assert empty.json() is None

        created = client.post(f"/api/v1/leads/{lead_id}/create-project")
        assert created.status_code == 201
        project_id = created.json()["project_id"]

        detail = client.get(f"/api/v1/projects/{project_id}")
        assert detail.status_code == 200
        assert len(detail.json()["tasks"]) >= 1
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_stock_return_write_off_and_project_reserve() -> None:
    client, engine = _client()
    try:
        sku = client.post(
            "/api/v1/inventory/skus",
            json={"code": "CAB-100", "name": "Кабинет", "category": "cabinet", "unit_cost": "1"},
        ).json()
        client.post(
            "/api/v1/inventory/transactions",
            json={"sku_id": sku["id"], "type": "RECEIPT", "quantity": "5"},
        )

        project = client.post("/api/v1/projects", json={"name": "Резервный"}).json()
        reserve = client.post(
            f"/api/v1/projects/{project['id']}/reservations",
            json={"sku_id": sku["id"], "quantity": "2", "note": "под монтаж"},
        )
        assert reserve.status_code == 201

        listed = client.get("/api/v1/inventory/skus?query=CAB")
        item = listed.json()[0]
        assert item["quantity_reserved"] == "2.000"

        write_off = client.post(
            "/api/v1/inventory/transactions",
            json={"sku_id": sku["id"], "type": "WRITE_OFF", "quantity": "1"},
        )
        assert write_off.status_code == 201

        returned = client.post(
            "/api/v1/inventory/transactions",
            json={
                "sku_id": sku["id"],
                "type": "RETURN",
                "quantity": "1",
                "project_id": project["id"],
            },
        )
        assert returned.status_code == 201

        timeline = client.get(f"/api/v1/projects/{project['id']}/timeline")
        assert timeline.status_code == 200
        kinds = {event["kind"] for event in timeline.json()}
        assert "stock" in kinds
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
