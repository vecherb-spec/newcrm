"""amoCRM-aligned deal pipeline stages table.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STAGES = [
    ("UNSORTED", "Неразобранное", 10, False, False, 88792562),
    ("NEW_LEAD", "Новая заявка", 20, False, False, 88792846),
    ("QUALIFICATION", "Квалификация", 30, False, False, 88792850),
    ("PROPOSAL_SENT", "КП отправлено", 40, False, False, 88792854),
    ("NEGOTIATION", "Переговоры", 50, False, False, 88792858),
    ("CONTRACT", "Договор", 60, False, False, 88792862),
    ("PREPAYMENT", "Предоплата", 70, False, False, 88792866),
    ("PRODUCTION", "Производство", 80, False, False, 88792870),
    ("DELIVERY", "Доставка", 90, False, False, 88792874),
    ("INSTALLATION", "Монтаж", 100, False, False, 88792878),
    ("ACT_SIGNING", "Подписание актов", 110, False, False, 88792882),
    ("CLOSED_WON", "Успешно реализовано", 10000, True, False, 142),
    ("CLOSED_LOST", "Закрыто и не реализовано", 11000, False, True, 143),
]


def upgrade() -> None:
    op.create_table(
        "lead_pipeline_stages",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_won", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_lost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("amo_status_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_lead_pipeline_stages_sort_order",
        "lead_pipeline_stages",
        ["sort_order"],
    )
    op.create_index(
        "ix_lead_pipeline_stages_amo_status_id",
        "lead_pipeline_stages",
        ["amo_status_id"],
        unique=True,
    )

    stage_table = sa.table(
        "lead_pipeline_stages",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_won", sa.Boolean),
        sa.column("is_lost", sa.Boolean),
        sa.column("amo_status_id", sa.Integer),
    )
    op.bulk_insert(
        stage_table,
        [
            {
                "code": code,
                "name": name,
                "sort_order": sort_order,
                "is_won": is_won,
                "is_lost": is_lost,
                "amo_status_id": amo_status_id,
            }
            for code, name, sort_order, is_won, is_lost, amo_status_id in STAGES
        ],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT"))
        op.execute(
            sa.text(
                """
                ALTER TABLE leads
                ALTER COLUMN status TYPE VARCHAR(40)
                USING (
                    CASE status::text
                        WHEN 'NEW' THEN 'NEW_LEAD'
                        WHEN 'CALCULATION' THEN 'QUALIFICATION'
                        ELSE status::text
                    END
                )
                """
            )
        )
        op.execute(sa.text("DROP TYPE IF EXISTS leadstatus"))
        op.execute(
            sa.text(
                """
                ALTER TABLE leads
                ADD CONSTRAINT fk_leads_pipeline_stage
                FOREIGN KEY (status) REFERENCES lead_pipeline_stages (code)
                """
            )
        )
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'NEW_LEAD'"))
    else:
        op.alter_column(
            "leads",
            "status",
            existing_type=sa.Enum(name="leadstatus"),
            type_=sa.String(40),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE leads DROP CONSTRAINT IF EXISTS fk_leads_pipeline_stage"))
        op.execute(
            sa.text(
                """
                CREATE TYPE leadstatus AS ENUM (
                    'NEW',
                    'QUALIFICATION',
                    'CALCULATION',
                    'PROPOSAL_SENT',
                    'NEGOTIATION',
                    'CLOSED_WON',
                    'CLOSED_LOST'
                )
                """
            )
        )
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status DROP DEFAULT"))
        op.execute(
            sa.text(
                """
                ALTER TABLE leads
                ALTER COLUMN status TYPE leadstatus
                USING (
                    CASE status
                        WHEN 'NEW_LEAD' THEN 'NEW'
                        WHEN 'UNSORTED' THEN 'NEW'
                        WHEN 'CONTRACT' THEN 'NEGOTIATION'
                        WHEN 'PREPAYMENT' THEN 'NEGOTIATION'
                        WHEN 'PRODUCTION' THEN 'NEGOTIATION'
                        WHEN 'DELIVERY' THEN 'NEGOTIATION'
                        WHEN 'INSTALLATION' THEN 'NEGOTIATION'
                        WHEN 'ACT_SIGNING' THEN 'NEGOTIATION'
                        ELSE status::leadstatus
                    END
                )
                """
            )
        )
        op.execute(sa.text("ALTER TABLE leads ALTER COLUMN status SET DEFAULT 'NEW'"))
    op.drop_index("ix_lead_pipeline_stages_amo_status_id", table_name="lead_pipeline_stages")
    op.drop_index("ix_lead_pipeline_stages_sort_order", table_name="lead_pipeline_stages")
    op.drop_table("lead_pipeline_stages")
