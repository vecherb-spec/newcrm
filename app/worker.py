from arq.connections import RedisSettings

from app.core.config import get_settings
from app.modules.inbox.adapters import EmailAdapter


async def generate_document_pdf(context: dict[str, object]) -> dict[str, object]:
    """Worker entrypoint reserved for a Playwright/WeasyPrint adapter."""
    return {"status": "queued-adapter", "document": context}


async def poll_email_inbox() -> dict[str, object]:
    """ARQ boundary for Yandex IMAP polling; network implementation lives in the adapter."""
    adapter = EmailAdapter(get_settings())
    if not adapter.is_connected():
        return {"status": "not_connected", "channel": "EMAIL"}
    items = await adapter.backfill()
    return {"status": "ok", "channel": "EMAIL", "items": len(items)}


class WorkerSettings:
    functions = [generate_document_pdf, poll_email_inbox]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
