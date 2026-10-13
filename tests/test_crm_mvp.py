import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_session
from app.main import app
from app.modules.inbox.adapters import SendResult
from app.modules.inbox.models import InboxChannel


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

        by_normalized_phone = client.get(
            "/api/v1/leads/lookup?phone=89990000000",
            headers=headers,
        )
        assert by_normalized_phone.status_code == 200
        assert by_normalized_phone.json()[0]["amo_id"] == "deal-42"

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
        assert any(task["title"] == "Позвонить по КП" for task in card["tasks"])
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


def test_real_amo_import_fixture_dry_run() -> None:
    client, engine = _client()
    try:
        _, service_token = _bootstrap_service_token(client)
        headers = {"Authorization": f"Bearer {service_token}"}
        fixture_path = Path(__file__).parent / "fixtures" / "crm_import_pending_1013.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        response = client.post(
            "/api/v1/imports/amo/deals?dry_run=true",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["dry_run"] is True
        assert result["created"] == 52
        assert result["notes_created"] == 68
        assert result["empty_stage_flagged"] >= 2

        lookup = client.get("/api/v1/leads/lookup?radist_chat_id=44395055", headers=headers)
        assert lookup.status_code == 200
        assert lookup.json() == []
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_tasks_module_bot_api_and_automatic_flags() -> None:
    client, engine = _client()
    try:
        admin_id, service_token = _bootstrap_service_token(client)
        headers = {"Authorization": f"Bearer {service_token}"}

        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"name": "Петр Клиент", "phone": "+79993334455", "company": "БЦ Восток"},
        ).json()
        lead = client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "title": "Экран в БЦ Восток",
                "status": "QUALIFICATION",
                "contact_id": contact["id"],
                "responsible_user_id": admin_id,
                "next_contact_at": "2026-10-13T18:00:00Z",
            },
        )
        assert lead.status_code == 201

        all_tasks = client.get("/api/v1/tasks?view=all", headers=headers)
        assert all_tasks.status_code == 200
        next_contact_tasks = [task for task in all_tasks.json() if task["kind"] == "next_contact"]
        assert len(next_contact_tasks) == 1
        assert next_contact_tasks[0]["lead_id"] == lead.json()["id"]

        standalone = client.post(
            "/api/v1/tasks",
            headers=headers,
            json={
                "title": "Проверить оплату",
                "due_at": "2026-10-12T12:00:00Z",
                "priority": "URGENT",
                "responsible_user_id": admin_id,
            },
        )
        assert standalone.status_code == 201
        assert standalone.json()["priority"] == "URGENT"

        overdue = client.get("/api/v1/tasks?view=overdue", headers=headers)
        assert overdue.status_code == 200
        assert any(task["id"] == standalone.json()["id"] for task in overdue.json())

        calendar = client.get(
            "/api/v1/tasks/calendar?start=2026-10-12&end=2026-10-14",
            headers=headers,
        )
        assert calendar.status_code == 200
        assert {task["title"] for task in calendar.json()} >= {
            "Проверить оплату",
            "Связаться по сделке: Экран в БЦ Восток",
        }

        completed = client.post(
            f"/api/v1/tasks/{standalone.json()['id']}/complete",
            headers=headers,
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "DONE"

        import_response = client.post(
            "/api/v1/imports/amo/deals",
            headers=headers,
            json=[
                {
                    "amo_id": "proposal-no-response",
                    "title": "КП без ответа",
                    "stage": "КП отправлено",
                    "amount": "100000",
                    "source": "amoCRM",
                    "created_at": "2026-10-01T10:00:00Z",
                    "contact": {"name": "Анна", "phone": "+79994445566"},
                    "notes": [],
                }
            ],
        )
        assert import_response.status_code == 200

        flags = client.get("/api/v1/tasks/proposal-no-response", headers=headers)
        assert flags.status_code == 200
        assert any(item["flag"] == "КП без ответа" for item in flags.json())

        dashboard = client.get("/api/v1/tasks/dashboard", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["no_response_proposals"] >= 1
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_inbox_radist_webhook_matching_and_mocked_send(monkeypatch) -> None:
    monkeypatch.setenv("RADIST_WEBHOOK_SECRET", "radist-secret")
    get_settings.cache_clear()
    client, engine = _client()
    try:
        _, service_token = _bootstrap_service_token(client)
        headers = {"Authorization": f"Bearer {service_token}"}
        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "name": "Клиент Inbox",
                "phone": "+79995550000",
                "radist_chat_id": "452764",
            },
        ).json()
        lead = client.post(
            "/api/v1/leads",
            headers=headers,
            json={"title": "Сделка Inbox", "contact_id": contact["id"]},
        ).json()

        channels = client.get("/api/v1/inbox/channels", headers=headers)
        assert channels.status_code == 200
        assert any(item["connected"] is False for item in channels.json())

        webhook = client.post(
            "/api/v1/webhooks/radist/radist-secret",
            json={
                "company_id": 510,
                "event_type": "messages.create",
                "event": {
                    "chat_id": 452764,
                    "chat": {
                        "id": 452764,
                        "name": "Клиент Inbox",
                        "phone": "79995550000",
                        "username": None,
                    },
                    "message": {
                        "message_id": "radist-message-1",
                        "direction": "inbound",
                        "message_type": "text",
                        "created_at": "2026-10-13T10:00:00+00:00",
                        "text": {"text": "Здравствуйте, нужен экран"},
                    },
                },
            },
        )
        assert webhook.status_code == 202

        conversations = client.get("/api/v1/inbox/conversations", headers=headers)
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert conversation["contact_id"] == contact["id"]
        assert conversation["lead_id"] == lead["id"]
        assert conversation["unread_count"] == 1

        detail = client.get(f"/api/v1/inbox/conversations/{conversation['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["messages"][0]["body"] == "Здравствуйте, нужен экран"

        lead_detail = client.get(f"/api/v1/leads/{lead['id']}", headers=headers).json()
        assert any("Входящее сообщение" in item["body"] for item in lead_detail["activities"])

        class FakeRadistAdapter:
            channel = InboxChannel.RADIST

            def is_connected(self) -> bool:
                return True

            async def send_message(self, message):
                assert message.text == "Ответ вручную"
                return SendResult(external_id="outbox-1", raw={"mock": True})

            async def backfill(self):
                return []

        monkeypatch.setattr(
            "app.modules.inbox.router.adapters_by_channel",
            lambda _settings: {InboxChannel.RADIST: FakeRadistAdapter()},
        )
        sent = client.post(
            f"/api/v1/inbox/conversations/{conversation['id']}/messages",
            headers=headers,
            json={"text": "Ответ вручную", "original_filename": "kp.pdf"},
        )
        assert sent.status_code == 201
        assert sent.json()["direction"] == "OUTBOUND"
        assert sent.json()["original_filename"] == "kp.pdf"
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        asyncio.run(engine.dispose())


def test_vk_callback_confirmation_and_message(monkeypatch) -> None:
    monkeypatch.setenv("VK_CONFIRMATION_CODE", "confirm-code")
    monkeypatch.setenv("VK_SECRET", "vk-secret")
    get_settings.cache_clear()
    client, engine = _client()
    try:
        _, service_token = _bootstrap_service_token(client)
        confirmation = client.post("/api/v1/webhooks/vk", json={"type": "confirmation"})
        assert confirmation.status_code == 200
        assert confirmation.text == "confirm-code"

        incoming = client.post(
            "/api/v1/webhooks/vk",
            json={
                "type": "message_new",
                "secret": "vk-secret",
                "object": {
                    "message": {
                        "id": 11,
                        "from_id": 123,
                        "peer_id": 123,
                        "text": "Сообщение из VK",
                    }
                },
            },
        )
        assert incoming.status_code == 200
        headers = {"Authorization": f"Bearer {service_token}"}
        conversations = client.get("/api/v1/inbox/conversations?channel=VK", headers=headers)
        assert conversations.status_code == 200
        assert conversations.json()[0]["title"] == "VK 123"
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        asyncio.run(engine.dispose())
