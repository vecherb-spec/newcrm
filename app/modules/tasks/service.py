from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Lead, LeadTask, TaskPriority, TaskStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def sync_next_contact_task(
    lead: Lead,
    author_id: UUID,
    session: AsyncSession,
) -> LeadTask | None:
    auto_key = f"lead:{lead.id}:next_contact"
    task = await session.scalar(select(LeadTask).where(LeadTask.auto_key == auto_key))
    if lead.next_contact_at is None:
        if task and task.status is not TaskStatus.DONE:
            task.status = TaskStatus.DONE
            task.is_completed = True
            task.completed_at = utc_now()
        return task

    title = f"Связаться по сделке: {lead.title}"
    if task is None:
        task = LeadTask(
            lead_id=lead.id,
            contact_id=lead.contact_id,
            title=title,
            due_at=lead.next_contact_at,
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            is_completed=False,
            responsible_user_id=lead.responsible_user_id or author_id,
            author_id=author_id,
            kind="next_contact",
            auto_key=auto_key,
        )
        session.add(task)
        await session.flush()
        return task

    task.title = title
    task.contact_id = lead.contact_id
    task.due_at = lead.next_contact_at
    task.responsible_user_id = lead.responsible_user_id or task.responsible_user_id or author_id
    if task.status is TaskStatus.DONE:
        task.status = TaskStatus.TODO
        task.is_completed = False
        task.completed_at = None
    return task
