import asyncio
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.inbox.adapters import EmailAdapter, RadistAdapter
from app.modules.inbox.email_imap import parse_raw_email
from app.modules.inbox.models import InboxChannel, InboxConversation, InboxMessage


def test_parse_raw_email_extracts_message_id_and_body() -> None:
    message = EmailMessage()
    message["Subject"] = "Тестовое письмо"
    message["From"] = "Client <client@example.com>"
    message["To"] = "info@medialive.ru"
    message["Message-ID"] = "<abc@example.com>"
    message["Date"] = "Mon, 13 Oct 2026 10:00:00 +0000"
    message.set_content("Нужен экран 3x2")

    parsed = parse_raw_email(message.as_bytes())
    assert parsed["message_id"] == "<abc@example.com>"
    assert parsed["sender_email"] == "client@example.com"
    assert parsed["body"] == "Нужен экран 3x2"


def test_email_adapter_backfill_uses_imap_mock(monkeypatch) -> None:
    monkeypatch.setenv("YANDEX_IMAP_USER", "info@medialive.ru")
    monkeypatch.setenv("YANDEX_APP_PASSWORD", "app-password")
    get_settings.cache_clear()

    def fake_fetch_messages_since(**_kwargs):
        return [
            {
                "message_id": "<mail-1@example.com>",
                "sender_name": "Client",
                "sender_email": "client@example.com",
                "subject": "Запрос КП",
                "body": "Пришлите КП",
                "occurred_at": datetime(2026, 10, 13, 10, 0, tzinfo=UTC),
                "attachments": [],
                "raw_headers": {},
            }
        ]

    monkeypatch.setattr(
        "app.modules.inbox.adapters.fetch_messages_since",
        fake_fetch_messages_since,
    )
    adapter = EmailAdapter(get_settings())
    items = asyncio.run(
        adapter.backfill(since=datetime(2026, 10, 1, tzinfo=UTC))
    )
    assert len(items) == 1
    assert items[0]["external_chat_id"] == "client@example.com"
    assert items[0]["messages"][0]["external_id"] == "<mail-1@example.com>"

    get_settings.cache_clear()


def test_radist_adapter_backfill_parses_chats_and_messages(monkeypatch) -> None:
    monkeypatch.setenv("RADIST_API_KEY", "radist-key")
    monkeypatch.setenv("RADIST_COMPANY_ID", "207300")
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, **kwargs):
            if url.endswith("/messaging/chats/with_contacts/"):
                return FakeResponse(
                    {
                        "items": [
                            {
                                "contact": {"name": "Клиент", "phone": "+79990000000"},
                                "chats": [{"chat_id": 452764, "name": "Клиент"}],
                            }
                        ]
                    }
                )
            if url.endswith("/messaging/messages/"):
                return FakeResponse(
                    {
                        "messages": [
                            {
                                "message_id": "radist-1",
                                "direction": "inbound",
                                "message_type": "text",
                                "created_at": "2026-10-13T10:00:00+00:00",
                                "text": {"text": "Здравствуйте"},
                            }
                        ]
                    }
                )
            raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("app.modules.inbox.adapters.httpx.AsyncClient", FakeClient)
    adapter = RadistAdapter(get_settings())
    items = asyncio.run(adapter.backfill(since=datetime(2026, 10, 1, tzinfo=UTC)))
    assert len(items) == 1
    assert items[0]["external_chat_id"] == "452764"
    assert items[0]["messages"][0]["body"] == "Здравствуйте"

    get_settings.cache_clear()


def test_ingest_backfill_persists_email_message(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base, get_session
    from app.main import app
    from app.modules.inbox.backfill import ingest_backfill_items

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
    client = TestClient(app)
    try:
        client.post(
            "/api/v1/auth/bootstrap",
            json={
                "email": "inbox-backfill@medialive.ru",
                "full_name": "Inbox QA",
                "password": "very-secure-password",
            },
        )
        login = client.post(
            "/api/v1/auth/token",
            data={
                "username": "inbox-backfill@medialive.ru",
                "password": "very-secure-password",
            },
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        contact = client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"name": "Email Client", "email": "client@example.com"},
        ).json()

        async def ingest() -> None:
            async with sessions() as session:
                stored = await ingest_backfill_items(
                    session,
                    channel=InboxChannel.EMAIL,
                    items=[
                        {
                            "external_chat_id": "client@example.com",
                            "conversation_title": "Запрос",
                            "contact": {"email": "client@example.com"},
                            "messages": [
                                {
                                    "external_id": "<mail-1@example.com>",
                                    "direction": "inbound",
                                    "body": "Привет",
                                    "occurred_at": "2026-10-13T10:00:00+00:00",
                                }
                            ],
                        }
                    ],
                )
                assert stored == 1
                conversation = await session.scalar(select(InboxConversation))
                assert conversation is not None
                assert str(conversation.contact_id) == contact["id"]
                message = await session.scalar(select(InboxMessage))
                assert message is not None
                assert message.external_id == "<mail-1@example.com>"

        asyncio.run(ingest())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
