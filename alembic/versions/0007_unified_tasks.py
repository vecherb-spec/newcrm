"""Expand CRM tasks into a unified task module.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _enum_column_type(name: str, values: tuple[str, ...]) -> sa.Enum:
    bind = op.get_bind()
    enum_type = sa.Enum(*values, name=name)
    if bind.dialect.name != "postgresql":
        return enum_type
    enum_type.create(bind, checkfirst=True)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    task_status = _enum_column_type("taskstatuscrm", ("TODO", "IN_PROGRESS", "DONE"))
    task_priority = _enum_column_type("taskpriority", ("LOW", "NORMAL", "HIGH", "URGENT"))

    op.alter_column("lead_tasks", "lead_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("lead_tasks", sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id")))
    op.add_column(
        "lead_tasks",
        sa.Column("status", task_status, nullable=False, server_default="TODO"),
    )
    op.add_column(
        "lead_tasks",
        sa.Column("priority", task_priority, nullable=False, server_default="NORMAL"),
    )
    op.add_column(
        "lead_tasks",
        sa.Column("responsible_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
    )
    op.add_column(
        "lead_tasks",
        sa.Column("kind", sa.String(50), nullable=False, server_default="manual"),
    )
    op.add_column("lead_tasks", sa.Column("auto_key", sa.String(160)))
    op.create_index("ix_lead_tasks_contact_id", "lead_tasks", ["contact_id"])
    op.create_index("ix_lead_tasks_responsible_user_id", "lead_tasks", ["responsible_user_id"])
    op.create_index("ix_lead_tasks_auto_key", "lead_tasks", ["auto_key"], unique=True)

    op.execute(
        sa.text(
            """
            UPDATE lead_tasks
            SET status = (
                CASE WHEN is_completed THEN 'DONE' ELSE 'TODO' END
            )::taskstatuscrm
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_lead_tasks_auto_key", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_responsible_user_id", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_contact_id", table_name="lead_tasks")
    op.drop_column("lead_tasks", "auto_key")
    op.drop_column("lead_tasks", "kind")
    op.drop_column("lead_tasks", "responsible_user_id")
    op.drop_column("lead_tasks", "priority")
    op.drop_column("lead_tasks", "status")
    op.drop_column("lead_tasks", "contact_id")
    op.alter_column("lead_tasks", "lead_id", existing_type=sa.Uuid(), nullable=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TYPE "taskpriority"'))
        op.execute(sa.text('DROP TYPE "taskstatuscrm"'))
