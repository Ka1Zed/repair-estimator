# app/tests/test_price_fallback.py
# Инвариант проекта (#159, #144): цена недоступна/невалидна из парсера → fallback на seed,
# расчёт не падает, нулевая цена парсера не возвращается и не закрепляется в кэше БД.

from decimal import Decimal

import pytest

from app.parsers.base import BaseParser, ParsedPrice
from app.services.price_aggregator_service import get_price, get_labor_price
from app.db.models import Material, MaterialPrice, PriceSource, LaborService, LaborPrice


class _ZeroParser(BaseParser):
    """Имитирует VPN/блок-страницу: HTTP 200, но цена нулевая (исключения нет)."""
    source_name = "Мегастрой"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        return ParsedPrice(price_min=Decimal(0), price_avg=Decimal(0), price_max=Decimal(0))


class _RaisingParser(BaseParser):
    """Парсер падает (сеть недоступна и т.п.)."""
    source_name = "Мегастрой"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        raise RuntimeError("сеть недоступна")


def _megastroy_price_row(db, material_name: str):
    material = db.query(Material).filter(Material.name == material_name).first()
    src = db.query(PriceSource).filter(PriceSource.name == "Мегастрой").first()
    return (
        db.query(MaterialPrice)
        .filter(
            MaterialPrice.material_id == material.id,
            MaterialPrice.source_id == src.id,
        )
        .first()
    )


@pytest.mark.usefixtures("setup_test_db")
def test_zero_parser_falls_back_to_seed_and_does_not_persist(db_session):
    """Парсер вернул 0 → отдаём seed (не 0), нулевую цену в БД НЕ сохраняем."""
    assert _megastroy_price_row(db_session, "Краска для стен") is None  # предусловие

    price = get_price("Краска для стен", parser=_ZeroParser())

    assert price is not None
    assert price.price_avg == Decimal("120")  # базовая seed-цена из conftest
    # Нулевая цена парсера не закрепилась в кэше.
    assert _megastroy_price_row(db_session, "Краска для стен") is None


@pytest.mark.usefixtures("setup_test_db")
def test_raising_parser_falls_back_to_seed(db_session):
    """Парсер бросил исключение → seed-цена, расчёт не падает (регресс ветки except)."""
    price = get_price("Краска для стен", parser=_RaisingParser())

    assert price is not None
    assert price.price_avg == Decimal("120")
    assert _megastroy_price_row(db_session, "Краска для стен") is None


@pytest.mark.usefixtures("setup_test_db")
def test_labor_prefers_parser_over_seed(db_session):
    """get_labor_price отдаёт валидную спарсенную (не-seed) цену вместо seed."""
    service = db_session.query(LaborService).filter(LaborService.name == "Покраска стен").first()
    src = db_session.query(PriceSource).filter(PriceSource.name == "Мегастрой").first()

    parsed_row = LaborPrice(
        labor_service_id=service.id, source_id=src.id,
        price_min=Decimal("900"), price_avg=Decimal("999"), price_max=Decimal("1100"),
    )
    db_session.add(parsed_row)
    db_session.commit()
    try:
        price = get_labor_price("Покраска стен", region=None)
        assert price is not None
        assert price.source_id == src.id          # источник — парсер, не seed
        assert price.price_avg == Decimal("999")  # не базовая seed-цена 450
    finally:
        # Чистим за собой: иначе parser-first сломает региональные seed-тесты.
        db_session.delete(parsed_row)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_falls_back_to_seed_when_no_parser_price(db_session):
    """Без спарсенной цены работа берётся из seed (значение > 0)."""
    price = get_labor_price("Покраска стен", region=None)
    assert price is not None
    assert price.price_avg == Decimal("450")  # базовая seed-цена из conftest
