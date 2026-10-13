"""Portal modules: warehouse ops, installations, project handoff.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _enum(name: str, values: tuple[str, ...]) -> sa.Enum:
    bind = op.get_bind()
    enum_type = sa.Enum(*values, name=name)
    if bind.dialect.name != "postgresql":
        return enum_type
    enum_type.create(bind, checkfirst=True)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE projectstatus ADD VALUE IF NOT EXISTS 'DELIVERY'"))

    op.add_column(
        "leads",
        sa.Column("contract_signed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "leads",
        sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "projects",
        sa.Column("calculation_id", sa.Uuid(), sa.ForeignKey("engineering_calculations.id")),
    )
    op.add_column("projects", sa.Column("amount", sa.Numeric(14, 2)))
    op.create_index("ix_projects_calculation_id", "projects", ["calculation_id"])

    crew_role = _enum(
        "crewrole",
        ("INSTALLER", "ENGINEER", "DRIVER", "CONTRACTOR"),
    )
    installation_status = _enum(
        "installationstatus",
        ("SCHEDULED", "IN_PROGRESS", "COMPLETED", "RESCHEDULED"),
    )

    op.create_table(
        "crew_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("role", crew_role, nullable=False),
    )
    op.create_index("ix_crew_members_role", "crew_members", ["role"])

    op.create_table(
        "installation_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", installation_status, nullable=False, server_default="SCHEDULED"),
        sa.Column("notes", sa.Text()),
        sa.Column("checklist", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_installation_jobs_project_id", "installation_jobs", ["project_id"])
    op.create_index("ix_installation_jobs_lead_id", "installation_jobs", ["lead_id"])
    op.create_index("ix_installation_jobs_starts_at", "installation_jobs", ["starts_at"])

    op.create_table(
        "installation_job_crew",
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("installation_jobs.id"), primary_key=True),
        sa.Column(
            "crew_member_id",
            sa.Uuid(),
            sa.ForeignKey("crew_members.id"),
            primary_key=True,
        ),
    )

    op.create_table(
        "project_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_project_notes_project_id", "project_notes", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_notes_project_id", table_name="project_notes")
    op.drop_table("project_notes")
    op.drop_table("installation_job_crew")
    op.drop_index("ix_installation_jobs_starts_at", table_name="installation_jobs")
    op.drop_index("ix_installation_jobs_lead_id", table_name="installation_jobs")
    op.drop_index("ix_installation_jobs_project_id", table_name="installation_jobs")
    op.drop_table("installation_jobs")
    op.drop_index("ix_crew_members_role", table_name="crew_members")
    op.drop_table("crew_members")
    op.drop_index("ix_projects_calculation_id", table_name="projects")
    op.drop_column("projects", "amount")
    op.drop_column("projects", "calculation_id")
    op.drop_column("leads", "paid")
    op.drop_column("leads", "contract_signed")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TYPE "installationstatus"'))
        op.execute(sa.text('DROP TYPE "crewrole"'))
