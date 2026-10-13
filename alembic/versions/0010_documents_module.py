"""Document generator module with templates and registry.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
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
    op.add_column("contacts", sa.Column("inn", sa.String(12)))
    op.add_column("contacts", sa.Column("kpp", sa.String(9)))
    op.add_column("contacts", sa.Column("ogrn", sa.String(15)))
    op.add_column("contacts", sa.Column("legal_address", sa.Text()))
    op.add_column("contacts", sa.Column("bank_name", sa.String(255)))
    op.add_column("contacts", sa.Column("bank_bik", sa.String(9)))
    op.add_column("contacts", sa.Column("bank_account", sa.String(34)))
    op.add_column("contacts", sa.Column("bank_corr_account", sa.String(34)))
    op.create_index("ix_contacts_inn", "contacts", ["inn"])

    doc_type = _enum(
        "documenttype",
        (
            "SUPPLY_CONTRACT",
            "INVOICE",
            "WAYBILL_UPD",
            "ACT",
            "QUOTE",
            "SPECIFICATION",
        ),
    )
    doc_status = _enum("documentstatus", ("DRAFT", "SENT", "SIGNED", "PAID"))

    op.create_table(
        "company_profile",
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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("inn", sa.String(12), nullable=False),
        sa.Column("kpp", sa.String(9)),
        sa.Column("ogrn", sa.String(15)),
        sa.Column("legal_address", sa.Text()),
        sa.Column("bank_name", sa.String(255)),
        sa.Column("bank_bik", sa.String(9)),
        sa.Column("bank_account", sa.String(34)),
        sa.Column("bank_corr_account", sa.String(34)),
        sa.Column("director_name", sa.String(160)),
        sa.Column("letterhead_html", sa.Text()),
    )

    op.create_table(
        "document_templates",
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
        sa.Column("doc_type", doc_type, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_document_templates_doc_type", "document_templates", ["doc_type"])

    op.create_table(
        "document_number_sequences",
        sa.Column("doc_type", doc_type, primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "generated_documents",
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
        sa.Column("root_id", sa.Uuid(), sa.ForeignKey("generated_documents.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("doc_type", doc_type, nullable=False),
        sa.Column("status", doc_status, nullable=False, server_default="DRAFT"),
        sa.Column("number", sa.String(80), nullable=False),
        sa.Column("number_year", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id")),
        sa.Column("calculation_id", sa.Uuid(), sa.ForeignKey("engineering_calculations.id")),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("document_templates.id")),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("vat_rate", sa.Numeric(5, 2)),
        sa.Column("vat_included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("context_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rendered_html", sa.Text()),
        sa.Column("scan_storage_key", sa.String(255)),
        sa.Column("finance_invoice_id", sa.Uuid(), sa.ForeignKey("invoices.id")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_generated_documents_doc_type", "generated_documents", ["doc_type"])
    op.create_index("ix_generated_documents_status", "generated_documents", ["status"])
    op.create_index("ix_generated_documents_lead_id", "generated_documents", ["lead_id"])
    op.create_index("ix_generated_documents_project_id", "generated_documents", ["project_id"])
    op.create_index("ix_generated_documents_number", "generated_documents", ["number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_generated_documents_number", table_name="generated_documents")
    op.drop_index("ix_generated_documents_project_id", table_name="generated_documents")
    op.drop_index("ix_generated_documents_lead_id", table_name="generated_documents")
    op.drop_index("ix_generated_documents_status", table_name="generated_documents")
    op.drop_index("ix_generated_documents_doc_type", table_name="generated_documents")
    op.drop_table("generated_documents")
    op.drop_table("document_number_sequences")
    op.drop_index("ix_document_templates_doc_type", table_name="document_templates")
    op.drop_table("document_templates")
    op.drop_table("company_profile")
    op.drop_index("ix_contacts_inn", table_name="contacts")
    op.drop_column("contacts", "bank_corr_account")
    op.drop_column("contacts", "bank_account")
    op.drop_column("contacts", "bank_bik")
    op.drop_column("contacts", "bank_name")
    op.drop_column("contacts", "legal_address")
    op.drop_column("contacts", "ogrn")
    op.drop_column("contacts", "kpp")
    op.drop_column("contacts", "inn")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TYPE "documentstatus"'))
        op.execute(sa.text('DROP TYPE "documenttype"'))
