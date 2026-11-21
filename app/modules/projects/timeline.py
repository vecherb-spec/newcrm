from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.installations.models import InstallationJob
from app.modules.inventory.models import StockTransaction
from app.modules.projects.models import ProjectNote, ProjectTask


async def build_project_timeline(session: AsyncSession, project_id: UUID) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    notes = await session.scalars(
        select(ProjectNote).where(ProjectNote.project_id == project_id)
    )
    for note in notes:
        events.append(
            {
                "kind": "note",
                "at": note.occurred_at,
                "title": "Заметка",
                "body": note.body,
                "meta": {"note_id": str(note.id)},
            }
        )

    tasks = await session.scalars(select(ProjectTask).where(ProjectTask.project_id == project_id))
    for task in tasks:
        events.append(
            {
                "kind": "checklist",
                "at": task.due_date or task.created_at,
                "title": task.title,
                "body": task.status.value,
                "meta": {
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                },
            }
        )

    installations = await session.scalars(
        select(InstallationJob).where(InstallationJob.project_id == project_id)
    )
    for job in installations:
        events.append(
            {
                "kind": "installation",
                "at": job.starts_at,
                "title": job.title,
                "body": job.address,
                "meta": {"job_id": str(job.id), "status": job.status.value},
            }
        )

    transactions = await session.scalars(
        select(StockTransaction)
        .where(StockTransaction.project_id == project_id)
        .order_by(StockTransaction.created_at.desc())
    )
    for tx in transactions:
        events.append(
            {
                "kind": "stock",
                "at": tx.created_at,
                "title": tx.type.value,
                "body": tx.note or tx.reference or "",
                "meta": {
                    "transaction_id": str(tx.id),
                    "sku_id": str(tx.sku_id),
                    "quantity": str(tx.quantity),
                },
            }
        )

    events.sort(key=lambda item: item["at"] or datetime.min.replace(tzinfo=UTC), reverse=True)
    return events