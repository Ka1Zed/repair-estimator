"""add finish_key/variant_tier to materials (#331)

Revision ID: d8b3c1f4a927
Revises: b3f6a1c9d7e2
Create Date: 2026-07-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd8b3c1f4a927'
down_revision: Union[str, Sequence[str], None] = 'b3f6a1c9d7e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug существующего родового материала -> finish_key позиции отделки (#331).
# Эти материалы становятся вариантом "стандарт" (variant_tier=avg) без потери
# id/цен — экономичные и премиальные варианты добавляются отдельно через seed.
_BACKFILL = {
    "laminate": "floor.laminate",
    "paint_walls": "walls.paint",
    "paint_ceiling": "ceiling.paint",
    "tile": "tile",
    "wallpaper": "walls.wallpaper",
    "socket": "socket",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('materials', sa.Column('finish_key', sa.String(), nullable=True))
    op.add_column('materials', sa.Column('variant_tier', sa.String(), nullable=True))
    op.create_index('ix_materials_finish_key', 'materials', ['finish_key'])

    conn = op.get_bind()
    for slug, finish_key in _BACKFILL.items():
        conn.execute(
            sa.text(
                "UPDATE materials SET finish_key = :finish_key, variant_tier = 'avg' "
                "WHERE slug = :slug"
            ),
            {"finish_key": finish_key, "slug": slug},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_materials_finish_key', table_name='materials')
    op.drop_column('materials', 'variant_tier')
    op.drop_column('materials', 'finish_key')
