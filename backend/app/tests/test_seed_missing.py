"""Тесты идемпотентного дозасева (#244).

seed_missing() должен добавлять недостающие позиции seed в непустую БД, НЕ
затирая существующие цены (в т.ч. собранные парсерами через update_prices).
"""
from decimal import Decimal

from app.db.seed import seed_missing
from app.db.session import SessionLocal
from app.db.models import Material, MaterialPrice, PriceSource


def test_seed_missing_restores_item_without_touching_parser_cache(isolated_seeded_db):
    # Готовим прод-подобное состояние: у отделочного материала лежит цена
    # парсера (её терять нельзя), а инженерная позиция «Розетка» отсутствует.
    prep = SessionLocal()
    kraska_id = prep.query(Material).filter_by(name="Краска для стен").first().id
    megastroy_id = prep.query(PriceSource).filter_by(name="Мегастрой").first().id
    prep.add(MaterialPrice(
        material_id=kraska_id, source_id=megastroy_id,
        price_min=Decimal("900"), price_avg=Decimal("999"), price_max=Decimal("1100"),
    ))
    rozetka = prep.query(Material).filter_by(name="Розетка").first()
    prep.query(MaterialPrice).filter_by(material_id=rozetka.id).delete()
    prep.delete(rozetka)
    prep.commit()
    prep.close()

    added = seed_missing()

    check = SessionLocal()
    try:
        # «Розетка» вернулась вместе с seed-ценами.
        assert added["materials"] == 1
        restored = check.query(Material).filter_by(name="Розетка").first()
        assert restored is not None
        assert check.query(MaterialPrice).filter_by(material_id=restored.id).count() > 0

        # Кэш парсера не затёрт и не задублирован seed-строкой.
        assert check.query(MaterialPrice).filter_by(
            source_id=megastroy_id, price_avg=Decimal("999"),
        ).count() == 1
        # У «Краски» уже были цены → дозасев их пропустил (без новых seed-дублей).
        seed_src_id = check.query(PriceSource).filter_by(name="seed").first().id
        kraska_seed = check.query(MaterialPrice).filter_by(
            material_id=kraska_id, source_id=seed_src_id, region=None,
        ).count()
        assert kraska_seed == 1
    finally:
        check.close()

    # Повторный прогон ничего не добавляет — идемпотентность.
    again = seed_missing()
    assert again == {
        "sources": 0, "materials": 0, "services": 0,
        "material_prices": 0, "labor_prices": 0,
    }
