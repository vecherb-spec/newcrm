"""Add unified messenger inbox.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
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
    inbox_channel = _enum(
        "inboxchannel",
        ("RADIST", "EMAIL", "VK", "TELEGRAM_LEGACY", "MAX_LEGACY"),
    )
    message_direction = _enum("messagedirection", ("INBOUND", "OUTBOUND"))
    message_status = _enum("messagestatus", ("RECEIVED", "SENT", "FAILED"))

    op.create_table(
        "inbox_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("channel", inbox_channel, nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id")),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id")),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("raw_profile", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inbox_conversations_channel", "inbox_conversations", ["channel"])
    op.create_index("ix_inbox_conversations_external_id", "inbox_conversations", ["external_id"])
    op.create_index("ix_inbox_conversations_contact_id", "inbox_conversations", ["contact_id"])
    op.create_index("ix_inbox_conversations_lead_id", "inbox_conversations", ["lead_id"])
    op.create_index("ix_inbox_conversations_last_message_at", "inbox_conversations", ["last_message_at"])
    op.create_unique_constraint(
        "uq_inbox_conversations_channel_external_id",
        "inbox_conversations",
        ["channel", "external_id"],
    )

    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("inbox_conversations.id"), nullable=False),
        sa.Column("channel", inbox_channel, nullable=False),
        sa.Column("external_id", sa.String(255), unique=True),
        sa.Column("direction", message_direction, nullable=False),
        sa.Column("status", message_status, nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("sender_name", sa.String(160)),
        sa.Column("sent_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("attachment_url", sa.Text()),
        sa.Column("attachment_mime", sa.String(120)),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inbox_messages_conversation_id", "inbox_messages", ["conversation_id"])
    op.create_index("ix_inbox_messages_channel", "inbox_messages", ["channel"])
    op.create_index("ix_inbox_messages_direction", "inbox_messages", ["direction"])
    op.create_index("ix_inbox_messages_sent_by_id", "inbox_messages", ["sent_by_id"])
    op.create_index("ix_inbox_messages_occurred_at", "inbox_messages", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_inbox_messages_occurred_at", table_name="inbox_messages")
    op.drop_index("ix_inbox_messages_sent_by_id", table_name="inbox_messages")
    op.drop_index("ix_inbox_messages_direction", table_name="inbox_messages")
    op.drop_index("ix_inbox_messages_channel", table_name="inbox_messages")
    op.drop_index("ix_inbox_messages_conversation_id", table_name="inbox_messages")
    op.drop_table("inbox_messages")
    op.drop_constraint(
        "uq_inbox_conversations_channel_external_id",
        "inbox_conversations",
        type_="unique",
    )
    op.drop_index("ix_inbox_conversations_last_message_at", table_name="inbox_conversations")
    op.drop_index("ix_inbox_conversations_lead_id", table_name="inbox_conversations")
    op.drop_index("ix_inbox_conversations_contact_id", table_name="inbox_conversations")
    op.drop_index("ix_inbox_conversations_external_id", table_name="inbox_conversations")
    op.drop_index("ix_inbox_conversations_channel", table_name="inbox_conversations")
    op.drop_table("inbox_conversations")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TYPE "messagestatus"'))
        op.execute(sa.text('DROP TYPE "messagedirection"'))
        op.execute(sa.text('DROP TYPE "inboxchannel"'))
