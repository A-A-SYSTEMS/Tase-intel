"""V1.0.1.0001 — baseline empty revision. Schema arrives in Batch 3."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cadf71a984a7'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline revision — no schema changes.
    pass


def downgrade() -> None:
    # Baseline revision — nothing to roll back.
    pass
