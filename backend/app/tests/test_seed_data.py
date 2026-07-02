# app/tests/test_seed_data.py
# Согласованность seed-JSON (#225): цены ссылаются на существующие позиции,
# вилки корректны, единицы электрики/сантехники заведены с ценами по всем регионам.
# Тест файловый (без БД и сети): `python -m app.db.seed` падает с KeyError,
# если цена ссылается на несуществующий материал/работу — ловим это здесь.

import json
from decimal import Decimal
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "db" / "seed_data"

REGIONS = {None, "Москва", "Санкт-Петербург", "Казань"}

# Позиции #225: единицы под works.electric / works.plumbing (имена — контракт для #222).
ELECTRIC_PLUMBING_MATERIALS = {
    "Кабель электрический": "м",
    "Розетка": "шт",
    "Светильник": "шт",
    "Труба водопроводная": "м",
}
ELECTRIC_PLUMBING_SERVICES = {
    "Прокладка кабеля": "м",
    "Монтаж розетки": "шт",
    "Монтаж светильника": "шт",
    "Монтаж труб": "м",
    "Сантехнические работы": "точка",
}


def _load(name: str):
    with open(SEED_PATH / name, encoding="utf-8") as file:
        return json.load(file)


def test_material_prices_reference_existing_materials_and_sources():
    materials = {m["name"] for m in _load("materials.json")}
    sources = {s["name"] for s in _load("price_sources.json")}
    for row in _load("material_prices.json"):
        assert row["material"] in materials, f"цена на несуществующий материал: {row['material']}"
        assert row["source"] in sources, f"неизвестный источник: {row['source']}"


def test_labor_prices_reference_existing_services_and_sources():
    services = {s["name"] for s in _load("labor_services.json")}
    sources = {s["name"] for s in _load("price_sources.json")}
    for row in _load("labor_prices.json"):
        assert row["service"] in services, f"цена на несуществующую работу: {row['service']}"
        assert row["source"] in sources, f"неизвестный источник: {row['source']}"


def test_price_ranges_are_ordered_and_positive():
    rows = _load("material_prices.json") + _load("labor_prices.json")
    for row in rows:
        low = Decimal(row["price_min"])
        avg = Decimal(row["price_avg"])
        high = Decimal(row["price_max"])
        name = row.get("material") or row.get("service")
        assert Decimal(0) < low <= avg <= high, f"сломанная вилка у «{name}» ({row.get('region')})"
        assert row.get("region") in REGIONS, f"неизвестный регион: {row.get('region')}"


def test_electric_plumbing_materials_seeded_with_units():
    materials = {m["name"]: m for m in _load("materials.json")}
    for name, unit in ELECTRIC_PLUMBING_MATERIALS.items():
        assert name in materials, f"нет материала «{name}»"
        assert materials[name]["unit"] == unit


def test_electric_plumbing_services_seeded_with_units():
    services = {s["name"]: s for s in _load("labor_services.json")}
    for name, unit in ELECTRIC_PLUMBING_SERVICES.items():
        assert name in services, f"нет работы «{name}»"
        assert services[name]["unit"] == unit


def test_electric_plumbing_prices_cover_all_regions():
    """Инвариант fallback: у каждой позиции есть базовая seed-цена (region null),
    парсеры эти единицы не покрывают → без цены строка сметы была бы нулевой."""
    material_regions: dict[str, set] = {}
    for row in _load("material_prices.json"):
        material_regions.setdefault(row["material"], set()).add(row.get("region"))
    labor_regions: dict[str, set] = {}
    for row in _load("labor_prices.json"):
        labor_regions.setdefault(row["service"], set()).add(row.get("region"))

    for name in ELECTRIC_PLUMBING_MATERIALS:
        assert material_regions.get(name, set()) == REGIONS, f"не все регионы у «{name}»"
    for name in ELECTRIC_PLUMBING_SERVICES:
        regions = labor_regions.get(name, set())
        if name == "Сантехнические работы":
            # старая позиция недели 1, заведена только с базовой ценой
            assert None in regions, f"нет базовой seed-цены у «{name}»"
        else:
            assert regions == REGIONS, f"не все регионы у «{name}»"
