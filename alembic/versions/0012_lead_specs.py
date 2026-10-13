"""LED deal card specs JSONB and configurable select options.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        json_type = postgresql.JSONB(astext_type=sa.Text())
    else:
        json_type = sa.JSON()
    op.add_column(
        "leads",
        sa.Column("specs", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_table(
        "lead_spec_field_options",
        sa.Column("field_key", sa.String(80), primary_key=True),
        sa.Column("options", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "crm_pricing_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "default_markup_coefficient",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="1.35",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO crm_pricing_settings (id, default_markup_coefficient) VALUES (1, 1.35)"
        )
    )


def downgrade() -> None:
    op.drop_table("crm_pricing_settings")
    op.drop_table("lead_spec_field_options")
    op.drop_column("leads", "specs")
