"""add substation_load_profiles table

Revision ID: 00810fa89676
Revises: e7a1b5c69d8f
Create Date: 2026-02-26 23:22:21.872964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '00810fa89676'
down_revision: Union[str, Sequence[str], None] = 'e7a1b5c69d8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('substation_load_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('substation_id', sa.Integer(), nullable=False),
    sa.Column('month', sa.SmallInteger(), nullable=False),
    sa.Column('hour', sa.SmallInteger(), nullable=False),
    sa.Column('load_low_kw', sa.Float(), nullable=False),
    sa.Column('load_high_kw', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['substation_id'], ['substations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('substation_id', 'month', 'hour', name='uq_sub_load_profile')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('substation_load_profiles')
