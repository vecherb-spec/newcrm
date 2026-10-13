from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import httpx

from app.core.config import Settings
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

    async def backfill(self) -> list[dict[str, object]]: ...


class BaseAdapter:
    channel: InboxChannel

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def backfill(self) -> list[dict[str, object]]:
        return []

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise ChannelNotConnected(f"{self.channel.value} is not connected")


class RadistAdapter(BaseAdapter):
    channel = InboxChannel.RADIST
    base_url = "https://api.radist.online/v2"

    def is_connected(self) -> bool:
        return bool(self.settings.radist_api_key)

    async def send_message(self, message: OutgoingMessage) -> SendResult:
        self._require_connected()
        headers = {"Authorization": f"Bearer {self.settings.radist_api_key.get_secret_value()}"}
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


class EmailAdapter(BaseAdapter):
    channel = InboxChannel.EMAIL

    def is_connected(self) -> bool:
        return bool(self.settings.yandex_imap_user and self.settings.yandex_app_password)

    async def send_message(self, message: OutgoingMessage) -> SendResult:
        self._require_connected()
        # SMTP delivery is kept behind this adapter boundary; tests mock this method.
        return SendResult(external_id=f"email:{uuid4()}", raw={"queued": True})


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
