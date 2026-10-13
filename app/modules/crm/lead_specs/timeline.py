from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.models import LeadActivity, LeadTask
from app.modules.inbox.models import InboxConversation, InboxMessage


async def build_lead_timeline(session: AsyncSession, lead_id: UUID) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    activities = await session.scalars(
        select(LeadActivity)
        .where(LeadActivity.lead_id == lead_id)
        .options(selectinload(LeadActivity.author))
        .order_by(LeadActivity.occurred_at.desc())
    )
    for activity in activities:
        kind = "stage_change" if activity.body.startswith("[stage]") else "activity"
        events.append(
            {
                "kind": kind,
                "at": activity.occurred_at or activity.created_at,
                "title": activity.type.value,
                "body": activity.body,
                "author": activity.author.full_name if activity.author else None,
                "meta": {"activity_id": str(activity.id), "type": activity.type.value},
            }
        )

    tasks = await session.scalars(
        select(LeadTask)
        .where(LeadTask.lead_id == lead_id)
        .options(selectinload(LeadTask.responsible_user))
        .order_by(LeadTask.created_at.desc())
    )
    for task in tasks:
        events.append(
            {
                "kind": "task",
                "at": task.due_at or task.created_at,
                "title": task.title,
                "body": "Задача по сделке",
                "author": task.responsible_user.full_name if task.responsible_user else None,
                "meta": {
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "is_completed": task.is_completed,
                    "due_at": task.due_at.isoformat() if task.due_at else None,
                },
            }
        )

    conversations = await session.scalars(
        select(InboxConversation).where(InboxConversation.lead_id == lead_id)
    )
    conversation_ids = [conversation.id for conversation in conversations]
    if conversation_ids:
        messages = await session.scalars(
            select(InboxMessage)
            .where(InboxMessage.conversation_id.in_(conversation_ids))
            .order_by(InboxMessage.occurred_at.desc(), InboxMessage.created_at.desc())
        )
        for message in messages:
            events.append(
                {
                    "kind": "message",
                    "at": message.occurred_at or message.created_at,
                    "title": f"{message.channel.value} · {message.direction.value}",
                    "body": message.body or message.original_filename or "",
                    "author": message.sender_name,
                    "meta": {
                        "message_id": str(message.id),
                        "channel": message.channel.value,
                        "direction": message.direction.value,
                    },
                }
            )

    events.sort(key=lambda item: item["at"] or datetime.min.replace(tzinfo=UTC), reverse=True)
    return events
