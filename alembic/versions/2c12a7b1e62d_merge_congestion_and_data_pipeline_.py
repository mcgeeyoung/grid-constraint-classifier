"""merge_congestion_and_data_pipeline_branches

Revision ID: 2c12a7b1e62d
Revises: f3802d323f36, r0m3g5b81i9j
Create Date: 2026-02-28 20:53:46.118084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c12a7b1e62d'
down_revision: Union[str, Sequence[str], None] = ('f3802d323f36', 'r0m3g5b81i9j')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
