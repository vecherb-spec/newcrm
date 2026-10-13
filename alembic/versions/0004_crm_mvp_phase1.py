"""Expand CRM deals, contacts and activity log.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _replace_lead_status_enum(new_to_old: bool = False) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if new_to_old:
        op.execute(
            sa.text(
                """
                CREATE TYPE leadstatus_old AS ENUM (
                    'NEW',
                    'QUALIFICATION',
                    'CALCULATING',
                    'PROPOSAL_SENT',
                    'CONTRACT_SIGNING',
                    'IN_PROJECT',
                    'CLOSED_WON',
                    'CLOSED_LOST'
                )
                """
            )
        )
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT"))
        op.execute(
            sa.text(
                """
                ALTER TABLE leads
                ALTER COLUMN status TYPE leadstatus_old
                USING (
                    CASE status::text
                        WHEN 'CALCULATION' THEN 'CALCULATING'
                        WHEN 'NEGOTIATION' THEN 'CONTRACT_SIGNING'
                        ELSE status::text
                    END
                )::leadstatus_old
                """
            )
        )
        op.execute(sa.text("DROP TYPE leadstatus"))
        op.execute(sa.text("ALTER TYPE leadstatus_old RENAME TO leadstatus"))
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'NEW'"))
        return

    op.execute(
        sa.text(
            """
            CREATE TYPE leadstatus_new AS ENUM (
                'NEW',
                'QUALIFICATION',
                'CALCULATION',
                'PROPOSAL_SENT',
                'NEGOTIATION',
                'CLOSED_WON',
                'CLOSED_LOST'
            )
            """
        )
    )
    op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT"))
    op.execute(
        sa.text(
            """
            ALTER TABLE leads
            ALTER COLUMN status TYPE leadstatus_new
            USING (
                CASE status::text
                    WHEN 'CALCULATING' THEN 'CALCULATION'
                    WHEN 'CONTRACT_SIGNING' THEN 'NEGOTIATION'
                    WHEN 'IN_PROJECT' THEN 'NEGOTIATION'
                    ELSE status::text
                END
            )::leadstatus_new
            """
        )
    )
    op.execute(sa.text("DROP TYPE leadstatus"))
    op.execute(sa.text("ALTER TYPE leadstatus_new RENAME TO leadstatus"))
    op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'NEW'"))


def upgrade() -> None:
    _replace_lead_status_enum()
    activity_type = sa.Enum("CALL", "MESSAGE", "MEETING", "COMMENT", name="activitytype")
    activity_type.create(op.get_bind(), checkfirst=True)

    op.add_column("leads", sa.Column("amount", sa.Numeric(14, 2)))
    op.add_column("leads", sa.Column("responsible_user_id", sa.Uuid(), sa.ForeignKey("users.id")))
    op.add_column("leads", sa.Column("next_contact_at", sa.DateTime(timezone=True)))
    op.add_column("leads", sa.Column("lost_reason", sa.Text()))
    op.create_index("ix_leads_contact_id", "leads", ["contact_id"])
    op.create_index("ix_leads_responsible_user_id", "leads", ["responsible_user_id"])
    op.create_index("ix_leads_next_contact_at", "leads", ["next_contact_at"])

    op.create_table(
        "lead_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("type", activity_type, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_lead_activities_lead_id", "lead_activities", ["lead_id"])
    op.create_index("ix_lead_activities_author_id", "lead_activities", ["author_id"])

    op.create_table(
        "lead_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_lead_tasks_lead_id", "lead_tasks", ["lead_id"])
    op.create_index("ix_lead_tasks_due_at", "lead_tasks", ["due_at"])
    op.create_index("ix_lead_tasks_author_id", "lead_tasks", ["author_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_tasks_author_id", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_due_at", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_lead_id", table_name="lead_tasks")
    op.drop_table("lead_tasks")
    op.drop_index("ix_lead_activities_author_id", table_name="lead_activities")
    op.drop_index("ix_lead_activities_lead_id", table_name="lead_activities")
    op.drop_table("lead_activities")

    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TYPE "activitytype"'))

    op.drop_index("ix_leads_next_contact_at", table_name="leads")
    op.drop_index("ix_leads_responsible_user_id", table_name="leads")
    op.drop_index("ix_leads_contact_id", table_name="leads")
    op.drop_column("leads", "lost_reason")
    op.drop_column("leads", "next_contact_at")
    op.drop_column("leads", "responsible_user_id")
    op.drop_column("leads", "amount")
    _replace_lead_status_enum(new_to_old=True)
