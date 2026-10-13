from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.core.database import session_factory
from app.modules.inbox.adapters import EmailAdapter
from app.modules.inbox.backfill import (
    effective_sync_since,
    ingest_backfill_items,
    last_channel_sync_at,
)
from app.modules.inbox.models import InboxChannel


async def generate_document_pdf(context: dict[str, object]) -> dict[str, object]:
    """Worker entrypoint reserved for a Playwright/WeasyPrint adapter."""
    return {"status": "queued-adapter", "document": context}


async def poll_email_inbox(_ctx: dict[str, object] | None = None) -> dict[str, object]:
    """Poll Yandex IMAP inbox and persist new messages."""
    adapter = EmailAdapter(get_settings())
    if not adapter.is_connected():
        return {"status": "not_connected", "channel": "EMAIL"}
    async with session_factory() as session:
        last_sync = await last_channel_sync_at(session, InboxChannel.EMAIL)
        since = effective_sync_since(last_sync)
        items = await adapter.backfill(since=since)
        stored = await ingest_backfill_items(session, channel=InboxChannel.EMAIL, items=items)
    return {"status": "ok", "channel": "EMAIL", "items": stored}


class WorkerSettings:
    functions = [generate_document_pdf, poll_email_inbox]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
    cron_jobs = [cron(poll_email_inbox, minute=set(range(0, 60, 2)), run_at_startup=True)]
