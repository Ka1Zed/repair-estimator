"""Тесты пере-калибровки seed-цен (#282).

refresh_seed_prices() должен обновлять price_min/avg/max у существующих seed-цен
значениями из seed_data/*.json, НЕ трогая цены других источников (кэш парсеров,
региональные не-seed), дозасевать недостающие позиции и быть идемпотентным.
"""
from decimal import Decimal

from app.db.seed import refresh_seed_prices
from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource


def test_refresh_updates_seed_price_without_touching_parser_cache(isolated_seeded_db):
    # Прод-подобное состояние: seed-цена «Плиточный клей» стоит на тестовом avg=120
    # (в seed_data он 25 ₽/кг — как раз баг #213), а рядом лежит цена парсера, её терять нельзя.
    prep = SessionLocal()
    klei = prep.query(Material).filter_by(name="Плиточный клей").first()
    seed_id = prep.query(PriceSource).filter_by(name="seed").first().id
    megastroy_id = prep.query(PriceSource).filter_by(name="Мегастрой").first().id
    prep.add(MaterialPrice(
        material_id=klei.id, source_id=megastroy_id,
        price_min=Decimal("480"), price_avg=Decimal("500"), price_max=Decimal("560"),
    ))
    prep.commit()
    klei_id = klei.id
    prep.close()

    stats = refresh_seed_prices()
    assert stats["prices_updated"] >= 1

    check = SessionLocal()
    try:
        # seed-цена клея приехала к калиброванному значению из seed_data (25 ₽/кг).
        seed_row = check.query(MaterialPrice).filter_by(
            material_id=klei_id, source_id=seed_id, region=None,
        ).one()
        assert seed_row.price_avg == Decimal("25.00")
        assert seed_row.price_min == Decimal("16.00")
        assert seed_row.price_max == Decimal("60.00")

        # Цена парсера не тронута.
        parser_row = check.query(MaterialPrice).filter_by(
            material_id=klei_id, source_id=megastroy_id,
        ).one()
        assert parser_row.price_avg == Decimal("500.00")
    finally:
        check.close()


def test_refresh_is_idempotent(isolated_seeded_db):
    refresh_seed_prices()  # первый прогон приводит БД к seed_data
    again = refresh_seed_prices()  # второй — ничего менять уже нечего
    assert again == {
        "sources": 0, "materials": 0, "services": 0,
        "prices_added": 0, "prices_updated": 0,
    }
