import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app
from app.modules.auth.router import get_current_user


def test_project_checklist_and_lifecycle() -> None:
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
            "/api/v1/projects",
            json={
                "name": "Монтаж экрана в ТЦ",
                "installation_date": "2026-10-10",
                "installation_address": "Москва",
            },
        )
        assert response.status_code == 201
        project = response.json()
        assert len(project["tasks"]) == 5
        assert project["tasks"][0]["status"] == "TODO"

        task = project["tasks"][0]
        updated_task = client.patch(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
            json={"status": "DONE", "assignee": "Иван Монтажник"},
        )
        assert updated_task.status_code == 200
        assert updated_task.json()["status"] == "DONE"

        updated_project = client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"status": "PRODUCTION", "delivery_status": "packed"},
        )
        assert updated_project.status_code == 200
        assert updated_project.json()["status"] == "PRODUCTION"
        assert updated_project.json()["tasks"][0]["status"] == "DONE"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_project_rejects_lead_that_is_not_won() -> None:
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
        lead = client.post("/api/v1/leads", json={"title": "Новый запрос"}).json()
        response = client.post(
            "/api/v1/projects",
            json={"name": "Ранний проект", "lead_id": lead["id"]},
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
