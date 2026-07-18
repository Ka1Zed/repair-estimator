"""backfill finish_key/variant_tier for primer/putty/plinth (#390)

Revision ID: a1c2e6f9b4d7
Revises: d8b3c1f4a927
Create Date: 2026-07-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c2e6f9b4d7'
down_revision: Union[str, Sequence[str], None] = 'd8b3c1f4a927'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Тот же паттерн, что и в d8b3c1f4a927 (#331): эти материалы уже существуют на
# проде (заведены до #390) и становятся вариантом "стандарт" без потери id/цен —
# эконом/премиум-варианты доезжают отдельными строками через seed_data (#390).
#
# Без этого backfill seed_missing()/refresh_seed_prices() (app/db/seed.py) не
# трогают finish_key/variant_tier уже существующих по name строк — они обновляют
# только цены и добавляют ОТСУТСТВУЮЩИЕ материалы. Поэтому на непустой прод-БД
# новые эконом/премиум SKU появились бы с finish_key, а старая "стандарт"-строка
# осталась бы с finish_key=NULL. resolve_material(db, "primer", tier="avg") тогда
# не находит вариант avg среди строк с finish_key="primer" (их только min/max) и
# по _FALLBACK_ORDER["avg"] = ("avg", "min", "max") тихо откатывается на "min" —
# дефолтная смета получила бы "Грунтовка эконом" вместо "Грунтовка".
_BACKFILL = {
    "primer": "primer",
    "putty_start": "putty_start",
    "putty_finish": "putty_finish",
    "plinth": "plinth",
}


def upgrade() -> None:
    """Upgrade schema."""
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
    conn = op.get_bind()
    for slug in _BACKFILL:
        conn.execute(
            sa.text(
                "UPDATE materials SET finish_key = NULL, variant_tier = NULL "
                "WHERE slug = :slug"
            ),
            {"slug": slug},
        )
