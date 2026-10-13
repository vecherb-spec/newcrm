"""Add contact messenger identifiers for imports and bot lookup.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("normalized_phone", sa.String(40)))
    op.add_column("contacts", sa.Column("telegram", sa.String(160)))
    op.add_column("contacts", sa.Column("vk", sa.String(160)))
    op.add_column("contacts", sa.Column("radist_chat_id", sa.String(80)))
    op.create_index("ix_contacts_normalized_phone", "contacts", ["normalized_phone"])
    op.create_index("ix_contacts_telegram", "contacts", ["telegram"])
    op.create_index("ix_contacts_vk", "contacts", ["vk"])
    op.create_index("ix_contacts_radist_chat_id", "contacts", ["radist_chat_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_radist_chat_id", table_name="contacts")
    op.drop_index("ix_contacts_vk", table_name="contacts")
    op.drop_index("ix_contacts_telegram", table_name="contacts")
    op.drop_index("ix_contacts_normalized_phone", table_name="contacts")
    op.drop_column("contacts", "radist_chat_id")
    op.drop_column("contacts", "vk")
    op.drop_column("contacts", "telegram")
    op.drop_column("contacts", "normalized_phone")
