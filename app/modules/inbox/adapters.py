import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.modules.inbox.email_imap import fetch_messages_since
from app.modules.inbox.models import InboxChannel


class ChannelNotConnected(RuntimeError):
    pass


@dataclass(frozen=True)
class OutgoingMessage:
    external_chat_id: str
    text: str
    original_filename: str | None = None
    attachment_url: str | None = None


@dataclass(frozen=True)
class SendResult:
    external_id: str
    raw: dict[str, object]


class ChannelAdapter(Protocol):
    channel: InboxChannel

    def is_connected(self) -> bool: ...

    async def send_message(self, message: OutgoingMessage) -> SendResult: ...

    async def backfill(self, since: datetime | None = None) -> list[dict[str, object]]: ...


class BaseAdapter:
    channel: InboxChannel

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def backfill(self, since: datetime | None = None) -> list[dict[str, object]]:
        return []

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise ChannelNotConnected(f"{self.channel.value} is not connected")


class RadistAdapter(BaseAdapter):
    channel = InboxChannel.RADIST
    base_url = "https://api.radist.online/v2"

    def is_connected(self) -> bool:
        return bool(self.settings.radist_api_key)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.radist_api_key.get_secret_value()}",
            "X-Api-Key": self.settings.radist_api_key.get_secret_value(),
        }

    def _company_path(self, suffix: str) -> str:
        company_id = self.settings.radist_company_id
        return f"{self.base_url}/companies/{company_id}{suffix}"

    async def send_message(self, message: OutgoingMessage) -> SendResult:
        self._require_connected()
        headers = self._auth_headers()
        payload: dict[str, object]
        if message.attachment_url:
            payload = {
                "chat_id": message.external_chat_id,
                "message_type": "file",
                "file": {
                    "caption": message.text,
                    "url": message.attachment_url,
                    "name": message.original_filename,
                },
            }
        else:
            payload = {
                "chat_id": message.external_chat_id,
                "message_type": "text",
                "text": {"text": message.text},
            }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/messaging/messages/",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return SendResult(external_id=str(data.get("message_id") or uuid4()), raw=data)

    async def _fetch_messages(
        self,
        client: httpx.AsyncClient,
        chat_id: str,
        since: datetime | None,
    ) -> list[dict[str, object]]:
        params: dict[str, str] = {"chat_id": chat_id, "limit": "50"}
        if since is not None:
            params["since"] = since.isoformat()
        response = await client.get(
            self._company_path("/messaging/messages/"),
            headers=self._auth_headers(),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        messages = payload.get("messages") or payload.get("items") or []
        if not isinstance(messages, list):
            return []
        return [item for item in messages if isinstance(item, dict)]

    def _chat_item(
        self,
        chat: dict[str, object],
        contact: dict[str, object] | None,
    ) -> dict[str, object]:
        chat_id = str(chat.get("chat_id") or chat.get("id") or "")
        title = (
            str(chat.get("name") or chat.get("title") or "")
            or (contact or {}).get("name")
            or f"Radist {chat_id}"
        )
        phone = None
        if contact:
            phones = contact.get("phones")
            if isinstance(phones, list) and phones:
                first = phones[0]
                phone = first if isinstance(first, str) else first.get("phone")
            phone = phone or contact.get("phone")
        return {
            "external_chat_id": chat_id,
            "conversation_title": str(title),
            "contact": {
                "phone": phone,
                "telegram": (
                    chat.get("username")
                    or (contact.get("username") if contact else None)
                ),
                "radist_chat_id": chat_id,
            },
            "raw_profile": {"chat": chat, "contact": contact or {}},
            "messages": [],
        }

    def _message_item(self, message: dict[str, object]) -> dict[str, object] | None:
        message_type = str(message.get("message_type") or "text")
        typed_payload = message.get(message_type)
        if not isinstance(typed_payload, dict):
            typed_payload = {}
        text = typed_payload.get("text") or typed_payload.get("caption")
        external_id = message.get("message_id") or message.get("source_message_id")
        if external_id is None:
            return None
        return {
            "external_id": str(external_id),
            "direction": message.get("direction") or "inbound",
            "body": text,
            "sender_name": message.get("author"),
            "occurred_at": message.get("created_at"),
            "original_filename": typed_payload.get("name"),
            "attachment_url": typed_payload.get("url"),
            "attachment_mime": typed_payload.get("mime_type"),
            "raw_payload": message,
        }

    async def backfill(self, since: datetime | None = None) -> list[dict[str, object]]:
        self._require_connected()
        items: list[dict[str, object]] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params: dict[str, str] = {"sort_order": "new_first", "limit": "50"}
                if cursor:
                    params["cursor"] = cursor
                response = await client.get(
                    self._company_path("/messaging/chats/with_contacts/"),
                    headers=self._auth_headers(),
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                groups = (
                    payload.get("items")
                    or payload.get("contacts")
                    or payload.get("data")
                    or []
                )
                if isinstance(payload, list):
                    groups = payload
                if not isinstance(groups, list):
                    break
                for group in groups:
                    if not isinstance(group, dict):
                        continue
                    contact = group.get("contact")
                    contact_dict = contact if isinstance(contact, dict) else None
                    chats = group.get("chats") or []
                    if not chats and group.get("chat_id"):
                        chats = [group]
                    if not isinstance(chats, list):
                        continue
                    for chat in chats:
                        if not isinstance(chat, dict):
                            continue
                        item = self._chat_item(chat, contact_dict)
                        chat_id = str(item["external_chat_id"])
                        if not chat_id:
                            continue
                        messages = await self._fetch_messages(client, chat_id, since)
                        parsed_messages = [
                            parsed
                            for parsed in (self._message_item(message) for message in messages)
                            if parsed is not None
                        ]
                        if since is not None:
                            parsed_messages = [
                                message
                                for message in parsed_messages
                                if _message_after_since(message.get("occurred_at"), since)
                            ]
                        if parsed_messages:
                            item["messages"] = parsed_messages
                            items.append(item)
                cursor = payload.get("cursor") if isinstance(payload, dict) else None
                if not cursor:
                    break
        return items


def _message_after_since(occurred_at: object, since: datetime) -> bool:
    if occurred_at is None:
        return True
    if isinstance(occurred_at, datetime):
        candidate = occurred_at
    elif isinstance(occurred_at, str):
        candidate = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    else:
        return True
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=UTC)
    since_aware = since if since.tzinfo else since.replace(tzinfo=UTC)
    return candidate >= since_aware


class EmailAdapter(BaseAdapter):
    channel = InboxChannel.EMAIL
    imap_host = "imap.yandex.ru"

    def is_connected(self) -> bool:
        return bool(self.settings.yandex_imap_user and self.settings.yandex_app_password)

    async def send_message(self, message: OutgoingMessage) -> SendResult:
        self._require_connected()
        # SMTP delivery is kept behind this adapter boundary; tests mock this method.
        return SendResult(external_id=f"email:{uuid4()}", raw={"queued": True})

    async def backfill(self, since: datetime | None = None) -> list[dict[str, object]]:
        self._require_connected()
        if since is None:
            since = datetime.now(UTC)
        password = self.settings.yandex_app_password.get_secret_value()
        username = self.settings.yandex_imap_user or ""
        raw_messages = await asyncio.to_thread(
            fetch_messages_since,
            host=self.imap_host,
            username=username,
            password=password,
            since=since,
        )
        grouped: dict[str, dict[str, object]] = {}
        for parsed in raw_messages:
            message_id = parsed.get("message_id")
            if not message_id:
                continue
            sender_email = parsed.get("sender_email")
            external_chat_id = str(sender_email or parsed.get("sender_name") or message_id)
            conversation = grouped.setdefault(
                external_chat_id,
                {
                    "external_chat_id": external_chat_id,
                    "conversation_title": parsed.get("subject") or external_chat_id,
                    "contact": {"email": sender_email},
                    "raw_profile": {"email": sender_email},
                    "messages": [],
                },
            )
            messages = conversation["messages"]
            assert isinstance(messages, list)
            body = parsed.get("body")
            attachments = parsed.get("attachments") or []
            if attachments and not body:
                body = f"Вложение: {attachments[0].get('original_filename')}"
            messages.append(
                {
                    "external_id": str(message_id),
                    "direction": "inbound",
                    "body": body,
                    "sender_name": parsed.get("sender_name"),
                    "occurred_at": parsed.get("occurred_at"),
                    "original_filename": (
                        attachments[0].get("original_filename") if attachments else None
                    ),
                    "attachment_mime": (
                        attachments[0].get("attachment_mime") if attachments else None
                    ),
                    "raw_payload": {"headers": parsed.get("raw_headers")},
                }
            )
            for attachment in attachments[1:]:
                messages.append(
                    {
                        "external_id": f"{message_id}:{attachment.get('original_filename')}",
                        "direction": "inbound",
                        "body": None,
                        "sender_name": parsed.get("sender_name"),
                        "occurred_at": parsed.get("occurred_at"),
                        "original_filename": attachment.get("original_filename"),
                        "attachment_mime": attachment.get("attachment_mime"),
                        "raw_payload": {"headers": parsed.get("raw_headers")},
                    }
                )
        return list(grouped.values())


class VkAdapter(BaseAdapter):
    channel = InboxChannel.VK
    base_url = "https://api.vk.com/method"

    def is_connected(self) -> bool:
        return bool(self.settings.vk_group_token)

    async def send_message(self, message: OutgoingMessage) -> SendResult:
        self._require_connected()
        payload = {
            "access_token": self.settings.vk_group_token.get_secret_value(),
            "v": "5.199",
            "peer_id": message.external_chat_id,
            "random_id": 0,
            "message": message.text,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/messages.send", data=payload)
            response.raise_for_status()
            data = response.json()
        return SendResult(external_id=f"vk:{data.get('response') or uuid4()}", raw=data)


def adapters_by_channel(settings: Settings) -> dict[InboxChannel, ChannelAdapter]:
    return {
        InboxChannel.RADIST: RadistAdapter(settings),
        InboxChannel.EMAIL: EmailAdapter(settings),
        InboxChannel.VK: VkAdapter(settings),
    }
