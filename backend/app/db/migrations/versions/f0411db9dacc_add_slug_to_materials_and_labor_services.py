"""add slug to materials and labor_services

Revision ID: f0411db9dacc
Revises: c7e2a9b14d83
Create Date: 2026-07-09 10:32:50.641208

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0411db9dacc'
down_revision: Union[str, Sequence[str], None] = 'c7e2a9b14d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Машинный ключ вместо поиска по кириллическому name в расчётных сервисах (#278).
# name/slug — 1:1, значения совпадают с seed_data/*.json и константами в
# material_calc_service.py / labor_calc_service.py / hidden_works_service.py.
MATERIAL_SLUGS = {
    # Легаси-строка с прод-БД: до разделения на стартовую/финишную (id=3
    # на проде) шпаклёвка была одной позицией — в текущем materials.json
    # её уже нет, но без записи в словаре бэкфилл валится на NOT NULL.
    "Шпаклевка": "putty_legacy",
    "Краска для стен": "paint_walls",
    "Краска для стен эконом": "paint_walls_economy",
    "Краска для стен премиум": "paint_walls_premium",
    "Грунтовка": "primer",
    "Шпаклевка стартовая": "putty_start",
    "Шпаклевка финишная": "putty_finish",
    "Ламинат": "laminate",
    "Ламинат эконом": "laminate_economy",
    "Ламинат премиум": "laminate_premium",
    "Линолеум": "linoleum",
    "Паркетная доска": "parquet",
    "Плинтус": "plinth",
    "Плитка": "tile",
    "Плитка эконом": "tile_economy",
    "Плитка премиум": "tile_premium",
    "Плиточный клей": "tile_adhesive",
    "Затирка": "grout",
    "Краска потолочная": "paint_ceiling",
    "Краска потолочная премиум": "paint_ceiling_premium",
    "Обои": "wallpaper",
    "Обои эконом": "wallpaper_economy",
    "Обои премиум": "wallpaper_premium",
    "Краска влагостойкая": "paint_moisture",
    "Кабель электрический": "cable",
    "Розетка": "socket",
    "Розетка эконом": "socket_economy",
    "Светильник": "light",
    "Труба водопроводная": "pipe",
}

LABOR_SERVICE_SLUGS = {
    "Покраска стен": "paint_walls",
    "Покраска потолка": "paint_ceiling",
    "Шпаклевка стен": "putty_walls",
    "Поклейка обоев": "wallpaper_gluing",
    "Укладка ламината": "lay_laminate",
    "Укладка линолеума": "lay_linoleum",
    "Укладка паркета": "lay_parquet",
    "Укладка плитки": "lay_tile",
    "Монтаж натяжного потолка": "stretch_ceiling",
    "Закладная под светильник": "ceiling_embed",
    "Ниша под карниз": "curtain_niche",
    "Отделка откосов": "otkos",
    "Электромонтаж": "electrical_install",
    "Штробление": "chasing",
    "Сантехнические работы": "plumbing_works",
    "Прокладка кабеля": "cable_lay",
    "Монтаж розетки": "socket_mount",
    "Монтаж светильника": "light_mount",
    "Монтаж труб": "pipe_mount",
    "Демонтаж": "demolition",
    "Выравнивание стен": "level_walls",
    "Стяжка пола": "screed_floor",
    "Гидроизоляция": "waterproof",
    "Грунтование": "priming",
}


def _backfill(table: str, slugs: dict[str, str]) -> None:
    conn = op.get_bind()
    for name, slug in slugs.items():
        conn.execute(
            sa.text(f"UPDATE {table} SET slug = :slug WHERE name = :name"),
            {"slug": slug, "name": name},
        )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('materials', sa.Column('slug', sa.String(), nullable=True))
    op.add_column('labor_services', sa.Column('slug', sa.String(), nullable=True))

    _backfill('materials', MATERIAL_SLUGS)
    _backfill('labor_services', LABOR_SERVICE_SLUGS)

    op.alter_column('materials', 'slug', nullable=False)
    op.alter_column('labor_services', 'slug', nullable=False)
    op.create_unique_constraint('uq_materials_slug', 'materials', ['slug'])
    op.create_unique_constraint('uq_labor_services_slug', 'labor_services', ['slug'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_labor_services_slug', 'labor_services', type_='unique')
    op.drop_constraint('uq_materials_slug', 'materials', type_='unique')
    op.drop_column('labor_services', 'slug')
    op.drop_column('materials', 'slug')
