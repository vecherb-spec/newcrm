import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.router import get_current_user
from app.modules.documents.amount_words import rubles_in_words
from app.modules.finance.models import EntryType, FinanceEntry, Invoice


def test_rubles_in_words() -> None:
    text = rubles_in_words(Decimal("125000.50"))
    assert "руб" in text
    assert "50 копеек" in text


def test_document_generate_numbering_and_paid_finance_sync() -> None:
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
        project = client.post("/api/v1/projects", json={"name": "Документы тест"}).json()
        lead = client.post(
            "/api/v1/leads",
            json={"title": "Сделка для счёта", "status": "CLOSED_WON", "amount": "250000"},
        ).json()

        templates = client.get("/api/v1/documents/templates")
        assert templates.status_code == 200
        assert len(templates.json()) >= 6

        generated = client.post(
            "/api/v1/documents/documents/generate",
            json={
                "doc_type": "INVOICE",
                "title": "Счёт на монтаж",
                "project_id": project["id"],
                "lead_id": lead["id"],
                "amount": "250000",
                "vat_rate": "20",
                "vat_included": True,
            },
        )
        assert generated.status_code == 201
        doc = generated.json()
        assert doc["number"].startswith("СЧ-")
        assert doc["status"] == "DRAFT"

        preview = client.get(f"/api/v1/documents/documents/{doc['id']}/preview")
        assert preview.status_code == 200
        assert "250000" in preview.text

        pdf = client.get(f"/api/v1/documents/documents/{doc['id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"

        paid = client.patch(
            f"/api/v1/documents/documents/{doc['id']}/status",
            json={"status": "PAID"},
        )
        assert paid.status_code == 200
        assert paid.json()["status"] == "PAID"

        async def check_finance() -> None:
            async with sessions() as session:
                invoice = await session.scalar(select(Invoice))
                assert invoice is not None
                assert invoice.status == "paid"
                entry = await session.scalar(
                    select(FinanceEntry).where(FinanceEntry.type == EntryType.REVENUE)
                )
                assert entry is not None
                assert entry.amount == Decimal("250000.00")

        asyncio.run(check_finance())

        registry = client.get("/api/v1/documents/documents?query=СЧ")
        assert registry.status_code == 200
        assert any(item["id"] == doc["id"] for item in registry.json())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
