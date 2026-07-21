"""add category_exclusions to materials (#406)

Revision ID: c4d9e1a7b2f6
Revises: a1c2e6f9b4d7
Create Date: 2026-07-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c4d9e1a7b2f6'
down_revision: Union[str, Sequence[str], None] = 'a1c2e6f9b4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug материала -> токены смежных категорий (#406). Латиница: source_url слаг
# транслитерирован (kraska-dlya-drevesiny-...). Товар «чужой», если slug содержит
# любой токен. Backfill в миграции нужен, чтобы прод получил проверку без
# пере-seed (как finish_key в d8b3c1f4a927) — держать в синхроне с
# seed_data/materials.json. Токены проставляем и вариантам эконом/премиум: они
# резолвятся отдельными Material в min_item/max_item.
_PAINT_TOKENS = ["drevesin", "dereva", "derevu", "po-metall", "po-metallu",
                 "fasad", "avtomobil", "dlya-pola"]
# У потолочной дополнительно исключаем «для стен» — стеновая краска это тоже
# смежная категория относительно потолочной.
_CEILING_TOKENS = _PAINT_TOKENS + ["dlya-sten"]
_BACKFILL = {
    "paint_walls": _PAINT_TOKENS,
    "paint_walls_economy": _PAINT_TOKENS,
    "paint_walls_premium": _PAINT_TOKENS,
    "paint_ceiling": _CEILING_TOKENS,
    "paint_ceiling_economy": _CEILING_TOKENS,
    "paint_ceiling_premium": _CEILING_TOKENS,
    "paint_moisture": _PAINT_TOKENS,
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('materials', sa.Column('category_exclusions', JSONB(), nullable=True))

    conn = op.get_bind()
    for slug, tokens in _BACKFILL.items():
        conn.execute(
            sa.text(
                "UPDATE materials SET category_exclusions = :tokens WHERE slug = :slug"
            ).bindparams(sa.bindparam("tokens", value=tokens, type_=JSONB())),
            {"slug": slug},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('materials', 'category_exclusions')
