"""owner -> owner_id

Revision ID: 0c8594b2befd
Revises: d92c425550eb
Create Date: 2026-02-05 18:41:18.373628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c8594b2befd'
down_revision: Union[str, Sequence[str], None] = 'd92c425550eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('pictures', 'owner', new_column_name='owner_id')

def downgrade() -> None:
    op.alter_column('pictures', 'owner_id', new_column_name='owner')