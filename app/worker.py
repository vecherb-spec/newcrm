from arq.connections import RedisSettings

from app.core.config import get_settings


async def generate_document_pdf(context: dict[str, object]) -> dict[str, object]:
    """Worker entrypoint reserved for a Playwright/WeasyPrint adapter."""
    return {"status": "queued-adapter", "document": context}


class WorkerSettings:
    functions = [generate_document_pdf]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
