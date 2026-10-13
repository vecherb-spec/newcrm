import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.router import get_current_user


def test_project_economics_entries_and_invoice_lifecycle() -> None:
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
    client = TestClient(app)
    try:
        project = client.post(
            "/api/v1/projects",
            json={"name": "Проект с финансами", "create_default_tasks": False},
        ).json()
        project_url = f"/api/v1/finance/projects/{project['id']}"
        entries = (
            {"type": "REVENUE", "amount": "100000", "description": "Оплата"},
            {"type": "MATERIAL", "amount": "30000", "description": "Модули"},
            {"type": "PAYROLL", "amount": "10000", "is_planned": True},
        )
        for entry in entries:
            response = client.post(f"{project_url}/entries", json=entry)
            assert response.status_code == 201

        economics = client.get(f"{project_url}/economics")
        assert economics.status_code == 200
        totals = economics.json()
        assert totals["actual_revenue"] == "100000.00"
        assert totals["actual_costs"] == "30000.00"
        assert totals["planned_costs"] == "10000.00"
        assert totals["gross_margin"] == "70000.00"
        assert totals["gross_margin_percent"] == "70.00"

        invoice = client.post(
            f"{project_url}/invoices",
            json={"number": "LED-001", "amount": "100000"},
        )
        assert invoice.status_code == 201
        assert invoice.json()["status"] == "draft"

        paid = client.patch(
            f"/api/v1/finance/invoices/{invoice.json()['id']}",
            json={"status": "paid"},
        )
        assert paid.status_code == 200
        assert paid.json()["status"] == "paid"

        invoice_pdf = client.get(f"/api/v1/documents/invoices/{invoice.json()['id']}.pdf")
        assert invoice_pdf.status_code == 200
        assert invoice_pdf.content.startswith(b"%PDF")

        act_pdf = client.get(f"/api/v1/documents/acts/{project['id']}.pdf")
        assert act_pdf.status_code == 200
        assert act_pdf.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
