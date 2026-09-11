"""Initial LED Ops schema.

Revision ID: 0001
"""

from alembic import op

from app.core.database import Base
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.projects import models as project_models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
