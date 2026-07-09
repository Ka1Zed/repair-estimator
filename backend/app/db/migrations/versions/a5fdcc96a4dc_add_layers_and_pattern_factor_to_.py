"""add layers and pattern_factor to materials

Revision ID: a5fdcc96a4dc
Revises: f0411db9dacc
Create Date: 2026-07-09 10:47:11.013287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5fdcc96a4dc'
down_revision: Union[str, Sequence[str], None] = 'f0411db9dacc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Число слоёв (unit='л', раньше LAYERS в material_calc_service.py) и надбавка
# на раппорт обоев (раньше WALLPAPER_PATTERN_FACTOR) — теперь колонки Material,
# значения совпадают с seed_data/materials.json (#278). Материалы без записи
# здесь остаются NULL -> дефолт 1 в quantity_of().
LAYERS_BY_SLUG = {
    "paint_walls": 2,
    "paint_ceiling": 2,
    "paint_moisture": 2,
    "primer": 1,
}
PATTERN_FACTOR_BY_SLUG = {
    "wallpaper": 1.3,
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('materials', sa.Column('layers', sa.Integer(), nullable=True))
    op.add_column('materials', sa.Column('pattern_factor', sa.Float(), nullable=True))

    conn = op.get_bind()
    for slug, layers in LAYERS_BY_SLUG.items():
        conn.execute(
            sa.text("UPDATE materials SET layers = :layers WHERE slug = :slug"),
            {"layers": layers, "slug": slug},
        )
    for slug, factor in PATTERN_FACTOR_BY_SLUG.items():
        conn.execute(
            sa.text("UPDATE materials SET pattern_factor = :factor WHERE slug = :slug"),
            {"factor": factor, "slug": slug},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('materials', 'pattern_factor')
    op.drop_column('materials', 'layers')
