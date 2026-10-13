import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import User
from app.modules.crm.models import ActivityType, Contact, Lead, LeadActivity
from app.modules.inbox.models import (
    InboxChannel,
    InboxConversation,
    InboxMessage,
    MessageDirection,
    MessageStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D+", "", phone)
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits or None


async def match_contact(
    session: AsyncSession,
    *,
    phone: str | None = None,
    telegram: str | None = None,
    vk: str | None = None,
    radist_chat_id: str | None = None,
    email: str | None = None,
) -> Contact | None:
    filters = []
    normalized_phone = normalize_phone(phone)
    if normalized_phone:
        filters.append(Contact.normalized_phone == normalized_phone)
    if telegram:
        filters.append(Contact.telegram == telegram)
    if vk:
        filters.append(Contact.vk == vk)
    if radist_chat_id:
        filters.append(Contact.radist_chat_id == radist_chat_id)
    if email:
        filters.append(Contact.email == email.casefold())
    if not filters:
        return None
    return await session.scalar(select(Contact).where(or_(*filters)))


async def latest_lead_for_contact(session: AsyncSession, contact_id: UUID | None) -> Lead | None:
    if not contact_id:
        return None
    return await session.scalar(
        select(Lead).where(Lead.contact_id == contact_id).order_by(Lead.created_at.desc())
    )


async def upsert_conversation(
    session: AsyncSession,
    *,
    channel: InboxChannel,
    external_id: str,
    title: str,
    contact: Contact | None,
    raw_profile: dict[str, object] | None = None,
) -> InboxConversation:
    conversation = await session.scalar(
        select(InboxConversation)
        .where(InboxConversation.channel == channel, InboxConversation.external_id == external_id)
        .options(selectinload(InboxConversation.contact), selectinload(InboxConversation.lead))
    )
    if conversation is None:
        lead = await latest_lead_for_contact(session, contact.id if contact else None)
        conversation = InboxConversation(
            channel=channel,
            external_id=external_id,
            title=title,
            contact_id=contact.id if contact else None,
            lead_id=lead.id if lead else None,
            unread_count=0,
            raw_profile=raw_profile or {},
        )
        session.add(conversation)
        await session.flush()
        return conversation
    conversation.title = title or conversation.title
    conversation.raw_profile = raw_profile or conversation.raw_profile
    if contact and conversation.contact_id is None:
        conversation.contact_id = contact.id
        lead = await latest_lead_for_contact(session, contact.id)
        conversation.lead_id = lead.id if lead else conversation.lead_id
    return conversation


async def record_message(
    session: AsyncSession,
    *,
    conversation: InboxConversation,
    direction: MessageDirection,
    body: str | None,
    external_id: str | None,
    occurred_at: datetime | str | None = None,
    sender_name: str | None = None,
    sent_by: User | None = None,
    original_filename: str | None = None,
    attachment_url: str | None = None,
    attachment_mime: str | None = None,
    raw_payload: dict[str, object] | None = None,
) -> InboxMessage:
    if external_id:
        existing = await session.scalar(
            select(InboxMessage).where(InboxMessage.external_id == external_id)
        )
        if existing:
            return existing
    message_status = (
        MessageStatus.RECEIVED if direction is MessageDirection.INBOUND else MessageStatus.SENT
    )
    message = InboxMessage(
        conversation_id=conversation.id,
        channel=conversation.channel,
        external_id=external_id,
        direction=direction,
        status=message_status,
        body=body,
        sender_name=sender_name,
        sent_by_id=sent_by.id if sent_by else None,
        occurred_at=parse_datetime(occurred_at) or utc_now(),
        original_filename=original_filename,
        attachment_url=attachment_url,
        attachment_mime=attachment_mime,
        raw_payload=raw_payload or {},
    )
    session.add(message)
    conversation.last_message_at = message.occurred_at
    if direction is MessageDirection.INBOUND:
        conversation.unread_count += 1
    await session.flush()
    if conversation.lead_id:
        prefix = (
            "Входящее сообщение"
            if direction is MessageDirection.INBOUND
            else "Исходящее сообщение"
        )
        content = body or original_filename or ""
        activity_body = f"{prefix} ({conversation.channel.value}): {content}".strip()
        session.add(
            LeadActivity(
                lead_id=conversation.lead_id,
                type=ActivityType.MESSAGE,
                body=activity_body,
                author_id=sent_by.id if sent_by else await _activity_author_id(session),
                occurred_at=message.occurred_at,
            )
        )
    return message


async def _activity_author_id(session: AsyncSession) -> UUID:
    user_id = await session.scalar(select(User.id).order_by(User.created_at))
    if user_id is None:
        raise RuntimeError("At least one user is required to log inbox activity")
    return user_id
