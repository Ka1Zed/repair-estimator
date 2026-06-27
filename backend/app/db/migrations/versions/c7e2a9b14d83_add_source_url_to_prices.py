"""add source_url to material_prices and labor_prices

Revision ID: c7e2a9b14d83
Revises: 1f0c4f032f48
Create Date: 2026-06-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7e2a9b14d83'
down_revision: Union[str, Sequence[str], None] = '1f0c4f032f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ссылка на карточку/страницу товара или услуги у источника цены.
    # Nullable: для seed-цен остаётся NULL, заполняется только парсером.
    op.add_column('material_prices', sa.Column('source_url', sa.String(), nullable=True))
    op.add_column('labor_prices', sa.Column('source_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('labor_prices', 'source_url')
    op.drop_column('material_prices', 'source_url')
