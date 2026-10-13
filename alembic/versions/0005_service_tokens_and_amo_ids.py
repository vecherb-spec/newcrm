"""Add service API tokens and amoCRM external ids.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("amo_id", sa.String(80)))
    op.add_column("leads", sa.Column("amo_id", sa.String(80)))
    op.create_index("ix_contacts_amo_id", "contacts", ["amo_id"], unique=True)
    op.create_index("ix_leads_amo_id", "leads", ["amo_id"], unique=True)

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
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
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"])
    op.create_index("ix_api_tokens_created_by_id", "api_tokens", ["created_by_id"])


def downgrade() -> None:
    op.drop_index("ix_api_tokens_created_by_id", table_name="api_tokens")
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_table("api_tokens")
    op.drop_index("ix_leads_amo_id", table_name="leads")
    op.drop_index("ix_contacts_amo_id", table_name="contacts")
    op.drop_column("leads", "amo_id")
    op.drop_column("contacts", "amo_id")
