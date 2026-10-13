import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import session_factory
from app.modules.auth.models import User
from app.modules.crm.models import LeadTask, TaskStatus
from app.modules.tasks.router import _filter_by_view, task_dashboard


def _postgres_url() -> str | None:
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql"):
        return database_url
    return None


@pytest.mark.skipif(_postgres_url() is None, reason="requires PostgreSQL DATABASE_URL")
async def test_overdue_filter_and_dashboard_on_postgres() -> None:
    async with session_factory() as session:
        user_id = await session.scalar(select(User.id).order_by(User.created_at))
        if user_id is None:
            pytest.skip("database has no users; run migrations first")
        overdue_due_at = datetime.now(UTC) - timedelta(days=1)
        task = LeadTask(
            title="Просроченная задача Postgres",
            due_at=overdue_due_at,
            status=TaskStatus.TODO,
            author_id=user_id,
            responsible_user_id=user_id,
        )
        session.add(task)
        await session.commit()

        statement = _filter_by_view(select(LeadTask), "overdue")
        result = await session.scalars(statement)
        ids = {item.id for item in result}
        assert task.id in ids

        dashboard = await task_dashboard(session=session)
        assert dashboard.overdue >= 1
