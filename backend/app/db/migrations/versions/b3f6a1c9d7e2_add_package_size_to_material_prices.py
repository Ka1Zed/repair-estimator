"""add package_size to material_prices

Revision ID: b3f6a1c9d7e2
Revises: e7a0f258c032
Create Date: 2026-07-11 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3f6a1c9d7e2'
down_revision: Union[str, Sequence[str], None] = 'e7a0f258c032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Фасовка конкретного товара за source_url (#306). Nullable: для seed/manual
    # остаётся NULL, заполняется только парсером — расчёт откатывается на
    # статичный Material.package_size, если тут NULL.
    op.add_column('material_prices', sa.Column('package_size', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('material_prices', 'package_size')
