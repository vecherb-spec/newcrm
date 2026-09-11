import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.router import get_current_user


def test_saved_calculation_is_recomputed_and_listed() -> None:
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
        response = client.post(
            "/api/v1/calculations",
            json={
                "name": "Тестовая версия <script>alert(1)</script>",
                "parameters": {"width_m": 2, "height_m": 1, "pitch_mm": 2.5},
            },
        )
        assert response.status_code == 201
        saved = response.json()
        assert saved["result"]["cabinet_count"] == 8
        assert saved["suggested_sales_price"] > saved["total_bom_cost"]

        listing = client.get("/api/v1/calculations")
        assert listing.status_code == 200
        assert listing.json()[0]["id"] == saved["id"]

        preview = client.get(f"/api/v1/documents/quotes/{saved['id']}/preview")
        assert preview.status_code == 200
        assert "<script>" not in preview.text
        assert "&lt;script&gt;" in preview.text

        pdf = client.get(f"/api/v1/documents/quotes/{saved['id']}.pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
