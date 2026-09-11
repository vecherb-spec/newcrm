import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.llm_client import LeadParser
from app.modules.crm.models import Lead, Message

router = APIRouter(prefix="/webhooks", tags=["Integrations"])


def _verify(received: str | None, expected: str | None) -> None:
    if expected and (not received or not hmac.compare_digest(received, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")


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
    external_id = str(message.get("message_id", ""))
    if not text or not external_id:
        return {"status": "ignored"}
    parsed = await LeadParser(settings).parse(text)
    lead = Lead(
        title=f"Telegram: {text[:80]}",
        source="telegram",
        raw_text=text,
        parsed_data=parsed.model_dump(mode="json"),
    )
    session.add(lead)
    await session.flush()
    session.add(
        Message(
            lead_id=lead.id,
            channel="telegram",
            external_id=f"telegram:{external_id}",
            body=text,
        )
    )
    await session.commit()
    return {"status": "accepted", "lead_id": str(lead.id)}
