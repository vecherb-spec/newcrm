"""Initial operations schema.

Revision ID: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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


def upgrade() -> None:
    lead_status = sa.Enum(
        "NEW",
        "QUALIFICATION",
        "CALCULATING",
        "PROPOSAL_SENT",
        "CONTRACT_SIGNING",
        "IN_PROJECT",
        "CLOSED_WON",
        "CLOSED_LOST",
        name="leadstatus",
    )
    project_status = sa.Enum(
        "PLANNING",
        "PROCUREMENT",
        "PRODUCTION",
        "INSTALLATION",
        "COMMISSIONING",
        "COMPLETED",
        name="projectstatus",
    )
    task_status = sa.Enum("TODO", "IN_PROGRESS", "BLOCKED", "DONE", name="taskstatus")
    stock_type = sa.Enum(
        "RECEIPT",
        "ISSUE",
        "ADJUSTMENT",
        "RESERVATION",
        "RELEASE",
        name="stocktransactiontype",
    )
    entry_type = sa.Enum(
        "REVENUE",
        "MATERIAL",
        "PAYROLL",
        "DELIVERY",
        "TRAVEL",
        "RENTAL",
        "OTHER",
        name="entrytype",
    )
    op.create_table(
        "contacts",
        _id(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(255)),
        sa.Column("company", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_contacts_phone", "contacts", ["phone"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_table(
        "leads",
        _id(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", lead_status, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("parsed_data", sa.JSON(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id")),
        *_timestamps(),
    )
    op.create_table(
        "messages",
        _id(),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False, unique=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_messages_lead_id", "messages", ["lead_id"])
    op.create_table(
        "projects",
        _id(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), unique=True),
        sa.Column("status", project_status, nullable=False),
        sa.Column("installation_date", sa.Date()),
        sa.Column("installation_address", sa.Text()),
        sa.Column("delivery_status", sa.String(50), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "project_tasks",
        _id(),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("assignee", sa.String(160)),
        sa.Column("status", task_status, nullable=False),
        sa.Column("due_date", sa.Date()),
        *_timestamps(),
    )
    op.create_index("ix_project_tasks_project_id", "project_tasks", ["project_id"])
    op.create_table(
        "skus",
        _id(),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantity_reserved", sa.Numeric(14, 3), nullable=False),
        sa.Column("minimum_stock", sa.Numeric(14, 3), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_skus_code", "skus", ["code"])
    op.create_index("ix_skus_category", "skus", ["category"])
    op.create_table(
        "stock_transactions",
        _id(),
        sa.Column("sku_id", sa.Uuid(), sa.ForeignKey("skus.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id")),
        sa.Column("type", stock_type, nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("reference", sa.String(255)),
        sa.Column("note", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_stock_transactions_sku_id", "stock_transactions", ["sku_id"])
    op.create_index("ix_stock_transactions_project_id", "stock_transactions", ["project_id"])
    op.create_table(
        "finance_entries",
        _id(),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", entry_type, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_planned", sa.Boolean(), nullable=False),
        sa.Column("occurred_on", sa.Date()),
        sa.Column("description", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_finance_entries_project_id", "finance_entries", ["project_id"])
    op.create_table(
        "invoices",
        _id(),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("number", sa.String(80), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("due_date", sa.Date()),
        *_timestamps(),
    )
    op.create_index("ix_invoices_project_id", "invoices", ["project_id"])


def downgrade() -> None:
    for table in (
        "invoices",
        "finance_entries",
        "stock_transactions",
        "skus",
        "project_tasks",
        "projects",
        "messages",
        "leads",
        "contacts",
    ):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        for enum_name in (
            "entrytype",
            "stocktransactiontype",
            "taskstatus",
            "projectstatus",
            "leadstatus",
        ):
            op.execute(sa.text(f'DROP TYPE "{enum_name}"'))
