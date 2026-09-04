"""empty message

Revision ID: bd9d4fc64b29
Revises: 8b65e739a4b8
Create Date: 2026-09-02 17:27:12.181219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd9d4fc64b29'
down_revision: Union[str, Sequence[str], None] = '8b65e739a4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
