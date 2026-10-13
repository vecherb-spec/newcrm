import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app


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
    return TestClient(app), engine


def _bootstrap_service_token(client: TestClient) -> tuple[str, str]:
    admin = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "admin@medialive.ru",
            "full_name": "Администратор",
            "password": "very-secure-password",
        },
    ).json()
    login = client.post(
        "/api/v1/auth/token",
        data={"username": "admin@medialive.ru", "password": "very-secure-password"},
    ).json()
    token_response = client.post(
        "/api/v1/auth/api-tokens",
        headers={"Authorization": f"Bearer {login['access_token']}"},
        json={"name": "sales bot"},
    )
    assert token_response.status_code == 201
    return admin["id"], token_response.json()["token"]


def test_crm_mvp_bot_api_deal_card_and_quote() -> None:
    client, engine = _client()
    try:
        admin_id, service_token = _bootstrap_service_token(client)
        headers = {"Authorization": f"Bearer {service_token}"}

        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "amo_id": "contact-42",
                "name": "Иван Петров",
                "phone": "+79990000000",
                "email": "ivan@example.ru",
                "company": "ТЦ Север",
            },
        )
        assert contact.status_code == 201

        lead = client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "amo_id": "deal-42",
                "title": "Экран для ТЦ Север",
                "stage": "КП отправлено",
                "status": "PROPOSAL_SENT",
                "source": "amoCRM",
                "amount": "1250000",
                "contact_id": contact.json()["id"],
                "responsible_user_id": admin_id,
                "next_contact_at": "2026-10-10T10:00:00Z",
            },
        )
        assert lead.status_code == 201
        lead_id = lead.json()["id"]

        by_amo = client.get("/api/v1/leads/lookup?amo_id=deal-42", headers=headers)
        assert by_amo.status_code == 200
        assert by_amo.json()[0]["id"] == lead_id

        by_phone = client.get("/api/v1/leads/lookup?phone=%2B79990000000", headers=headers)
        assert by_phone.status_code == 200
        assert by_phone.json()[0]["amo_id"] == "deal-42"

        activity = client.post(
            f"/api/v1/leads/{lead_id}/activities",
            headers=headers,
            json={"type": "CALL", "body": "Обсудили сроки поставки"},
        )
        assert activity.status_code == 201
        assert activity.json()["author"]["full_name"] == "Администратор"

        task = client.post(
            f"/api/v1/leads/{lead_id}/tasks",
            headers=headers,
            json={"title": "Позвонить по КП", "due_at": "2026-10-11T10:00:00Z"},
        )
        assert task.status_code == 201
        done = client.patch(
            f"/api/v1/leads/{lead_id}/tasks/{task.json()['id']}",
            headers=headers,
            json={"is_completed": True},
        )
        assert done.status_code == 200
        assert done.json()["is_completed"] is True

        calculation = client.post(
            "/api/v1/calculations",
            headers=headers,
            json={
                "name": "КП ТЦ Север",
                "lead_id": lead_id,
                "parameters": {"width_m": 3, "height_m": 2, "pitch_mm": 2.5},
            },
        )
        assert calculation.status_code == 201

        detail = client.get(f"/api/v1/leads/{lead_id}", headers=headers)
        assert detail.status_code == 200
        card = detail.json()
        assert card["contact"]["company"] == "ТЦ Север"
        assert card["activities"][0]["body"] == "Обсудили сроки поставки"
        assert card["tasks"][0]["title"] == "Позвонить по КП"
        assert card["calculations"][0]["name"] == "КП ТЦ Север"

        preview = client.get(
            f"/api/v1/documents/quotes/{calculation.json()['id']}/preview",
            headers=headers,
        )
        assert preview.status_code == 200
        assert "ООО «МЕДИАЛАЙВ»" in preview.text
        assert "СРОКИ ПОСТАВКИ ЭКРАНА ЗАКАЗЧИКУ: 20 рабочих дней" in preview.text
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_amo_import_is_idempotent_by_amo_id() -> None:
    client, engine = _client()
    try:
        _, service_token = _bootstrap_service_token(client)
        headers = {"Authorization": f"Bearer {service_token}"}
        payload = [
            {
                "amo_id": "amo-100",
                "title": "Экран на фасад",
                "stage": "Закрыто успешно",
                "amount": "900000",
                "source": "amoCRM",
                "created_at": "2026-09-01T09:00:00Z",
                "contact": {
                    "name": "Мария Соколова",
                    "phone": "+79991112233",
                    "email": "maria@example.ru",
                    "company": "Ресторан Волга",
                },
                "notes": [
                    {
                        "type": "звонок",
                        "text": "Клиент подтвердил заказ",
                        "created_at": "2026-09-02T12:00:00Z",
                        "author": "amo менеджер",
                    }
                ],
            }
        ]

        first = client.post("/api/v1/imports/amo/deals", headers=headers, json=payload)
        assert first.status_code == 200
        assert first.json()["created"] == 1
        assert first.json()["notes_created"] == 1

        second = client.post("/api/v1/imports/amo/deals", headers=headers, json=payload)
        assert second.status_code == 200
        assert second.json()["created"] == 0
        assert second.json()["updated"] == 1
        assert second.json()["notes_created"] == 0

        lookup = client.get("/api/v1/leads/lookup?amo_id=amo-100", headers=headers)
        assert lookup.status_code == 200
        assert lookup.json()[0]["status"] == "CLOSED_WON"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
