from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.modules.auth.router import CurrentUser
from app.modules.crm.models import Contact, Lead
from app.modules.crm.schemas import ContactRead, LeadRead
from app.modules.inbox.adapters import ChannelNotConnected, OutgoingMessage, adapters_by_channel
from app.modules.inbox.models import InboxChannel, InboxConversation, InboxMessage, MessageDirection
from app.modules.inbox.service import record_message

router = APIRouter(prefix="/inbox", tags=["Inbox"])


class ChannelStatus(BaseModel):
    channel: InboxChannel
    label: str
    connected: bool


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: InboxChannel
    external_id: str
    title: str
    unread_count: int
    contact_id: UUID | None
    lead_id: UUID | None
    contact: ContactRead | None = None
    last_message_at: datetime | None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    channel: InboxChannel
    external_id: str | None
    direction: MessageDirection
    body: str | None
    sender_name: str | None
    original_filename: str | None
    attachment_url: str | None
    occurred_at: datetime | None


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = Field(default_factory=list)


class ConversationLink(BaseModel):
    contact_id: UUID | None = None
    lead_id: UUID | None = None


class SendMessagePayload(BaseModel):
    text: str = Field(min_length=1)
    original_filename: str | None = Field(default=None, max_length=255)
    attachment_url: str | None = None


class ConversationLeadCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    source: str = Field(default="inbox", max_length=50)


def _conversation_options() -> tuple[object, ...]:
    return (
        selectinload(InboxConversation.contact),
        selectinload(InboxConversation.lead),
        selectinload(InboxConversation.messages),
    )


async def _require_conversation(
    conversation_id: UUID,
    session: AsyncSession,
) -> InboxConversation:
    conversation = await session.scalar(
        select(InboxConversation)
        .where(InboxConversation.id == conversation_id)
        .options(*_conversation_options())
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return conversation


@router.get("/channels", response_model=list[ChannelStatus])
async def channel_status(settings: Settings = Depends(get_settings)) -> list[ChannelStatus]:
    adapters = adapters_by_channel(settings)
    labels = {
        InboxChannel.RADIST: "Radist / Max / Telegram / WhatsApp",
        InboxChannel.EMAIL: "Email info@medialive.ru",
        InboxChannel.VK: "VK",
    }
    return [
        ChannelStatus(channel=channel, label=labels[channel], connected=adapter.is_connected())
        for channel, adapter in adapters.items()
    ]


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(
    channel: InboxChannel | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[InboxConversation]:
    statement = select(InboxConversation).options(selectinload(InboxConversation.contact))
    if channel:
        statement = statement.where(InboxConversation.channel == channel)
    statement = statement.order_by(InboxConversation.last_message_at.desc().nullslast())
    return list(await session.scalars(statement))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> InboxConversation:
    conversation = await _require_conversation(conversation_id, session)
    conversation.unread_count = 0
    await session.commit()
    return conversation


@router.patch("/conversations/{conversation_id}/link", response_model=ConversationRead)
async def link_conversation(
    conversation_id: UUID,
    payload: ConversationLink,
    session: AsyncSession = Depends(get_session),
) -> InboxConversation:
    conversation = await _require_conversation(conversation_id, session)
    if payload.contact_id and await session.get(Contact, payload.contact_id) is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    if payload.lead_id and await session.get(Lead, payload.lead_id) is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    conversation.contact_id = payload.contact_id
    conversation.lead_id = payload.lead_id
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.post("/conversations/{conversation_id}/lead", response_model=LeadRead)
async def create_lead_from_conversation(
    conversation_id: UUID,
    payload: ConversationLeadCreate,
    session: AsyncSession = Depends(get_session),
) -> Lead:
    conversation = await _require_conversation(conversation_id, session)
    lead = Lead(title=payload.title, source=payload.source, contact_id=conversation.contact_id)
    session.add(lead)
    await session.flush()
    conversation.lead_id = lead.id
    await session.commit()
    await session.refresh(lead)
    return lead


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: UUID,
    payload: SendMessagePayload,
    actor: CurrentUser,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> InboxMessage:
    conversation = await _require_conversation(conversation_id, session)
    adapter = adapters_by_channel(settings).get(conversation.channel)
    if adapter is None or not adapter.is_connected():
        raise HTTPException(status_code=409, detail="Канал не подключен")
    try:
        result = await adapter.send_message(
            OutgoingMessage(
                external_chat_id=conversation.external_id,
                text=payload.text,
                original_filename=payload.original_filename,
                attachment_url=payload.attachment_url,
            )
        )
    except ChannelNotConnected as error:
        raise HTTPException(status_code=409, detail="Канал не подключен") from error
    message = await record_message(
        session,
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        body=payload.text,
        external_id=result.external_id,
        sent_by=actor,
        original_filename=payload.original_filename,
        attachment_url=payload.attachment_url,
        raw_payload=result.raw,
    )
    await session.commit()
    await session.refresh(message)
    return message


@router.post("/radist/backfill")
async def radist_backfill(
    settings: Settings = Depends(get_settings),
) -> dict[str, int | str]:
    adapter = adapters_by_channel(settings)[InboxChannel.RADIST]
    if not adapter.is_connected():
        return {"status": "not_connected", "items": 0}
    items = await adapter.backfill()
    return {"status": "ok", "items": len(items)}
