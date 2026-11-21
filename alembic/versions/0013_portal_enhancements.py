"""Portal enhancements: project specs, crew flag, stock RETURN/WRITE_OFF.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        json_type = postgresql.JSONB(astext_type=sa.Text())
        op.execute(sa.text("ALTER TYPE stocktransactiontype ADD VALUE IF NOT EXISTS 'RETURN'"))
        op.execute(sa.text("ALTER TYPE stocktransactiontype ADD VALUE IF NOT EXISTS 'WRITE_OFF'"))
    else:
        json_type = sa.JSON()

    op.add_column(
        "projects",
        sa.Column("responsible_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("projects", sa.Column("deadline", sa.Date(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("specs", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "projects",
        sa.Column("files", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_projects_responsible_user_id", "projects", ["responsible_user_id"])

    op.add_column(
        "crew_members",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("crew_members", "is_internal")
    op.drop_index("ix_projects_responsible_user_id", table_name="projects")
    op.drop_column("projects", "files")
    op.drop_column("projects", "specs")
    op.drop_column("projects", "deadline")
    op.drop_column("projects", "responsible_user_id")