import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inbox.models import InboxChannel, InboxMessage, MessageDirection
from app.modules.inbox.service import match_contact, record_message, upsert_conversation

logger = logging.getLogger(__name__)


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


def _message_direction(message: dict[str, Any]) -> MessageDirection:
    direction_name = str(message.get("direction") or "inbound").casefold()
    if direction_name in {"outbound", "out", "outgoing"}:
        return MessageDirection.OUTBOUND
    return MessageDirection.INBOUND


async def _ingest_backfill_item(
    session: AsyncSession,
    *,
    channel: InboxChannel,
    item: dict[str, Any],
) -> int:
    stored = 0
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
        await record_message(
            session,
            conversation=conversation,
            direction=_message_direction(message),
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
    return stored


async def _mark_backfill_item_skipped(
    session: AsyncSession,
    *,
    channel: InboxChannel,
    item: dict[str, Any],
    reason: str,
) -> int:
    """Persist skip markers so sync cursor (max occurred_at) advances past bad rows."""
    messages = item.get("messages") or []
    if not messages:
        return 0
    contact_hints = item.get("contact") or {}
    contact = await match_contact(
        session,
        phone=contact_hints.get("phone"),
        telegram=contact_hints.get("telegram"),
        vk=contact_hints.get("vk"),
        radist_chat_id=contact_hints.get("radist_chat_id"),
        email=contact_hints.get("email"),
    )
    title = str(item.get("conversation_title") or item["external_chat_id"])
    conversation = await upsert_conversation(
        session,
        channel=channel,
        external_id=str(item["external_chat_id"]),
        title=title,
        contact=contact,
        raw_profile=item.get("raw_profile"),
    )
    stored = 0
    for message in messages:
        external_id = message.get("external_id")
        if not external_id:
            continue
        existing = await session.scalar(
            select(InboxMessage).where(InboxMessage.external_id == str(external_id))
        )
        if existing is not None:
            continue
        await record_message(
            session,
            conversation=conversation,
            direction=_message_direction(message),
            body=None,
            external_id=str(external_id),
            occurred_at=message.get("occurred_at"),
            sender_name=message.get("sender_name"),
            original_filename=message.get("original_filename"),
            attachment_url=message.get("attachment_url"),
            attachment_mime=message.get("attachment_mime"),
            raw_payload={
                "skipped": True,
                "skip_reason": reason[:1000],
                **(message.get("raw_payload") or {}),
            },
        )
        stored += 1
    return stored


async def ingest_backfill_items(
    session: AsyncSession,
    *,
    channel: InboxChannel,
    items: list[dict[str, Any]],
) -> int:
    stored = 0
    for item in items:
        external_chat_id = item.get("external_chat_id")
        try:
            count = await _ingest_backfill_item(session, channel=channel, item=item)
            stored += count
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Inbox backfill rejected item channel=%s external_chat_id=%s",
                channel.value,
                external_chat_id,
            )
            try:
                count = await _mark_backfill_item_skipped(
                    session,
                    channel=channel,
                    item=item,
                    reason="ingest_failed",
                )
                stored += count
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Inbox backfill could not mark skip channel=%s external_chat_id=%s",
                    channel.value,
                    external_chat_id,
                )
    return stored