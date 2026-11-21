"""Widen inbox text fields for long email subjects.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "inbox_conversations",
        "title",
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "inbox_messages",
        "sender_name",
        existing_type=sa.String(160),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "inbox_messages",
        "original_filename",
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "inbox_messages",
        "original_filename",
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.alter_column(
        "inbox_messages",
        "sender_name",
        existing_type=sa.Text(),
        type_=sa.String(160),
        existing_nullable=True,
    )
    op.alter_column(
        "inbox_conversations",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=False,
    )