from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inbox.models import InboxChannel, InboxMessage, MessageDirection
from app.modules.inbox.service import match_contact, record_message, upsert_conversation


def utc_now() -> datetime:
    return datetime.now(UTC)


async def last_channel_sync_at(session: AsyncSession, channel: InboxChannel) -> datetime | None:
    return await session.scalar(
        select(func.max(InboxMessage.occurred_at)).where(InboxMessage.channel == channel)
    )


def effective_sync_since(
    last_sync: datetime | None,
    *,
    initial_window_days: int = 30,
) -> datetime:
    floor = utc_now() - timedelta(days=initial_window_days)
    if last_sync is None:
        return floor
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=UTC)
    return max(last_sync, floor)


async def ingest_backfill_items(
    session: AsyncSession,
    *,
    channel: InboxChannel,
    items: list[dict[str, Any]],
) -> int:
    stored = 0
    for item in items:
        contact_hints = item.get("contact") or {}
        contact = await match_contact(
            session,
            phone=contact_hints.get("phone"),
            telegram=contact_hints.get("telegram"),
            vk=contact_hints.get("vk"),
            radist_chat_id=contact_hints.get("radist_chat_id"),
            email=contact_hints.get("email"),
        )
        conversation = await upsert_conversation(
            session,
            channel=channel,
            external_id=str(item["external_chat_id"]),
            title=str(item.get("conversation_title") or item["external_chat_id"]),
            contact=contact,
            raw_profile=item.get("raw_profile"),
        )
        for message in item.get("messages") or []:
            direction_name = str(message.get("direction") or "inbound").casefold()
            direction = (
                MessageDirection.OUTBOUND
                if direction_name in {"outbound", "out", "outgoing"}
                else MessageDirection.INBOUND
            )
            await record_message(
                session,
                conversation=conversation,
                direction=direction,
                body=message.get("body"),
                external_id=message.get("external_id"),
                occurred_at=message.get("occurred_at"),
                sender_name=message.get("sender_name"),
                original_filename=message.get("original_filename"),
                attachment_url=message.get("attachment_url"),
                attachment_mime=message.get("attachment_mime"),
                raw_payload=message.get("raw_payload"),
            )
            stored += 1
    if stored:
        await session.commit()
    return stored
