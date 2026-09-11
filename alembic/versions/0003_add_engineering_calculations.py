"""Add versioned engineering calculation snapshots.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineering_calculations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id")),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=False),
        sa.Column("total_bom_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("suggested_sales_price", sa.Numeric(14, 2), nullable=False),
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
    op.create_index(
        "ix_engineering_calculations_lead_id",
        "engineering_calculations",
        ["lead_id"],
    )
    op.create_index(
        "ix_engineering_calculations_created_by_id",
        "engineering_calculations",
        ["created_by_id"],
    )


def downgrade() -> None:
    op.drop_table("engineering_calculations")
