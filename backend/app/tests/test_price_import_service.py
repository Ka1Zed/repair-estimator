# app/tests/test_price_import_service.py
# CSV-импорт цен (import_prices_from_csv): валидные строки материалов/работ
# записываются, битые/неизвестные — пропускаются с пометкой, порядок вилки
# min<=avg<=max сохраняется. Пишет в БД → фикстура isolated_seeded_db
# пересобирает канонический seed до и после теста.

from decimal import Decimal

import pytest

from app.db.models import LaborPrice, LaborService, Material, MaterialPrice, PriceSource
from app.services.price_import_service import import_prices_from_csv

# Импорт мутирует общую тест-БД (пишет цены) — изолируем seed.
pytestmark = pytest.mark.usefixtures("isolated_seeded_db")

SOURCE = "Мегастрой"  # источник есть в seed price_sources


def _material_price(db, material_name, source_name):
    mat = db.query(Material).filter(Material.name == material_name).first()
    src = db.query(PriceSource).filter(PriceSource.name == source_name).first()
    return (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.material_id == mat.id,
            MaterialPrice.source_id == src.id,
            MaterialPrice.region.is_(None),
        )
        .first()
    )


def _labor_price(db, service_name, source_name):
    svc = db.query(LaborService).filter(LaborService.name == service_name).first()
    src = db.query(PriceSource).filter(PriceSource.name == source_name).first()
    return (
        db.query(LaborPrice)
        .filter(
            LaborPrice.labor_service_id == svc.id,
            LaborPrice.source_id == src.id,
            LaborPrice.region.is_(None),
        )
        .first()
    )


def test_imports_valid_material_and_labor(db_session):
    '''Валидные строки материала и работы записываются, updated=2, skipped пуст.'''
    csv_text = (
        "kind,name,price_min,price_avg,price_max\n"
        "material,Краска для стен,300,350,400\n"
        "labor,Покраска стен,500,600,700\n"
    )
    result = import_prices_from_csv(csv_text, source_name=SOURCE)

    assert result["updated"] == 2
    assert result["skipped"] == []

    db_session.expire_all()
    mp = _material_price(db_session, "Краска для стен", SOURCE)
    assert mp is not None
    assert (mp.price_min, mp.price_avg, mp.price_max) == (
        Decimal(300), Decimal(350), Decimal(400),
    )
    lp = _labor_price(db_session, "Покраска стен", SOURCE)
    assert lp is not None
    assert (lp.price_min, lp.price_avg, lp.price_max) == (
        Decimal(500), Decimal(600), Decimal(700),
    )


def test_preserves_price_spread_order(db_session):
    '''Записанная вилка сохраняет порядок min<=avg<=max из CSV.'''
    csv_text = (
        "kind,name,price_min,price_avg,price_max\n"
        "material,Краска для стен,120.50,180.75,240.90\n"
    )
    import_prices_from_csv(csv_text, source_name=SOURCE)

    db_session.expire_all()
    mp = _material_price(db_session, "Краска для стен", SOURCE)
    assert mp.price_min <= mp.price_avg <= mp.price_max
    assert mp.price_avg == Decimal("180.75")


def test_skips_broken_rows_but_imports_valid(db_session):
    '''Битые строки (плохой kind, пустое имя, мусор в цене, неизвестное имя)
    пропускаются с пометкой; валидная строка всё равно импортируется.'''
    csv_text = (
        "kind,name,price_min,price_avg,price_max\n"
        "material,Краска для стен,300,350,400\n"   # ok
        "gizmo,Краска для стен,1,2,3\n"            # плохой kind
        "material,,1,2,3\n"                         # пустое имя
        "material,Краска для стен,abc,2,3\n"        # цена не число
        "material,Несуществующий материал,1,2,3\n"  # нет такого материала
        "labor,Нет такой услуги,1,2,3\n"            # нет такой услуги
    )
    result = import_prices_from_csv(csv_text, source_name=SOURCE)

    assert result["updated"] == 1
    assert len(result["skipped"]) == 5

    db_session.expire_all()
    mp = _material_price(db_session, "Краска для стен", SOURCE)
    assert mp is not None
    assert mp.price_avg == Decimal(350)


def test_missing_price_column_skips_row(db_session):
    '''Отсутствие колонки цены → строка пропущена, а не падение импорта.'''
    csv_text = "kind,name,price_min,price_avg\nmaterial,Краска для стен,300,350\n"
    result = import_prices_from_csv(csv_text, source_name=SOURCE)

    assert result["updated"] == 0
    assert len(result["skipped"]) == 1


def test_unknown_source_raises():
    '''Источник, которого нет в price_sources, → RuntimeError (нужен seed).'''
    csv_text = "kind,name,price_min,price_avg,price_max\nmaterial,Краска для стен,1,2,3\n"
    with pytest.raises(RuntimeError):
        import_prices_from_csv(csv_text, source_name="нет-такого-источника")
