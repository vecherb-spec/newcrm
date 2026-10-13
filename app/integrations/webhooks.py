import hmac
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.llm_client import LeadParser
from app.modules.crm.models import Contact, Lead, Message
from app.modules.inbox.models import InboxChannel, MessageDirection
from app.modules.inbox.service import match_contact, record_message, upsert_conversation

router = APIRouter(prefix="/webhooks", tags=["Integrations"])


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D+", "", phone)
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits or None


def _verify(received: str | None, expected: str | None) -> None:
    if expected and (not received or not hmac.compare_digest(received, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")


def _secret_value(secret: object | None) -> str | None:
    return secret.get_secret_value() if secret else None


async def _ingest_message(
    *,
    channel: str,
    external_id: str,
    text: str,
    session: AsyncSession,
    settings: Settings,
) -> dict[str, str]:
    message_id = f"{channel}:{external_id}"
    existing = await session.scalar(select(Message).where(Message.external_id == message_id))
    if existing:
        return {"status": "duplicate"}
    parsed = await LeadParser(settings).parse(text)
    contact = None
    if parsed.contact_name or parsed.contact_phone:
        contact = Contact(
            name=parsed.contact_name or "Клиент из мессенджера",
            phone=parsed.contact_phone,
            normalized_phone=_normalize_phone(parsed.contact_phone),
            company=parsed.location,
        )
        session.add(contact)
        await session.flush()
    lead = Lead(
        title=f"{channel.title()}: {text[:80]}",
        source=channel,
        raw_text=text,
        parsed_data=parsed.model_dump(mode="json"),
        contact_id=contact.id if contact else None,
    )
    session.add(lead)
    await session.flush()
    session.add(
        Message(
            lead_id=lead.id,
            channel=channel,
            external_id=message_id,
            body=text,
        )
    )
    await session.commit()
    return {"status": "accepted", "lead_id": str(lead.id)}


@router.post("/telegram", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    expected = (
        settings.telegram_webhook_secret.get_secret_value()
        if settings.telegram_webhook_secret
        else None
    )
    _verify(x_telegram_bot_api_secret_token, expected)
    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message") or {}
    text = message.get("text") or message.get("caption")
    chat_id = (message.get("chat") or {}).get("id", "")
    message_id = message.get("message_id")
    if not text or not message_id:
        return {"status": "ignored"}
    external_id = f"{chat_id}:{message_id}"
    return await _ingest_message(
        channel="telegram",
        external_id=external_id,
        text=text,
        session=session,
        settings=settings,
    )


@router.post("/max", status_code=status.HTTP_202_ACCEPTED)
async def max_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    expected = (
        settings.max_webhook_secret.get_secret_value() if settings.max_webhook_secret else None
    )
    _verify(x_webhook_secret, expected)
    payload = await request.json()
    message = payload.get("message") or payload
    text = message.get("text") or message.get("body")
    external_id = str(message.get("id") or message.get("message_id") or "")
    if not text or not external_id:
        return {"status": "ignored"}
    return await _ingest_message(
        channel="max",
        external_id=external_id,
        text=text,
        session=session,
        settings=settings,
    )


@router.post("/radist/{secret}", status_code=status.HTTP_202_ACCEPTED)
async def radist_webhook(
    secret: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    expected = _secret_value(settings.radist_webhook_secret)
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")
    payload = await request.json()
    if payload.get("event_type") != "messages.create":
        return {"status": "ignored"}
    event = payload.get("event") or {}
    chat = event.get("chat") or {}
    message = event.get("message") or {}
    chat_id = str(event.get("chat_id") or chat.get("id") or message.get("chat_id") or "")
    if not chat_id:
        return {"status": "ignored"}
    message_type = message.get("message_type") or "text"
    typed_payload = message.get(message_type) or {}
    if not isinstance(typed_payload, dict):
        typed_payload = {}
    text = typed_payload.get("text") or typed_payload.get("caption")
    original_filename = typed_payload.get("name")
    attachment_url = typed_payload.get("url")
    attachment_mime = typed_payload.get("mime_type")
    contact = await match_contact(
        session,
        phone=chat.get("phone"),
        telegram=chat.get("username"),
        radist_chat_id=chat_id,
    )
    conversation = await upsert_conversation(
        session,
        channel=InboxChannel.RADIST,
        external_id=chat_id,
        title=chat.get("name") or chat.get("phone") or f"Radist {chat_id}",
        contact=contact,
        raw_profile=chat,
    )
    await record_message(
        session,
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        body=text,
        external_id=(
            str(message.get("message_id") or message.get("source_message_id"))
            if message.get("message_id") or message.get("source_message_id")
            else None
        ),
        occurred_at=message.get("created_at"),
        sender_name=message.get("author") or chat.get("name"),
        original_filename=original_filename,
        attachment_url=attachment_url,
        attachment_mime=attachment_mime,
        raw_payload=payload,
    )
    await session.commit()
    return {"status": "accepted"}


@router.post("/vk")
async def vk_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    payload = await request.json()
    event_type = payload.get("type")
    if event_type == "confirmation":
        code = _secret_value(settings.vk_confirmation_code)
        return Response(content=code or "", media_type="text/plain")
    expected_secret = _secret_value(settings.vk_secret)
    if expected_secret and payload.get("secret") != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")
    if event_type != "message_new":
        return Response(content="ok", media_type="text/plain")
    message = (payload.get("object") or {}).get("message") or {}
    peer_id = str(message.get("peer_id") or message.get("from_id") or "")
    if not peer_id:
        return Response(content="ok", media_type="text/plain")
    contact = await match_contact(session, vk=str(message.get("from_id") or peer_id))
    conversation = await upsert_conversation(
        session,
        channel=InboxChannel.VK,
        external_id=peer_id,
        title=f"VK {peer_id}",
        contact=contact,
        raw_profile={"peer_id": peer_id, "from_id": message.get("from_id")},
    )
    await record_message(
        session,
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        body=message.get("text"),
        external_id=f"vk:{message.get('id') or message.get('conversation_message_id')}",
        occurred_at=None,
        sender_name=str(message.get("from_id") or ""),
        raw_payload=payload,
    )
    await session.commit()
    return Response(content="ok", media_type="text/plain")
