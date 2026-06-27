# app/tests/test_price_fallback.py
# Инвариант проекта (#159, #144): цена недоступна/невалидна из парсера → fallback на seed,
# расчёт не падает, нулевая цена парсера не возвращается и не закрепляется в кэше БД.

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import settings
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


@pytest.mark.usefixtures("setup_test_db")
def test_labor_stale_parser_price_falls_back_to_seed(db_session):
    """Устаревшая (старше PRICE_TTL_HOURS) parser-цена игнорируется → отдаём seed (#167)."""
    service = db_session.query(LaborService).filter(LaborService.name == "Покраска стен").first()
    src = db_session.query(PriceSource).filter(PriceSource.name == "Мегастрой").first()
    stale_at = datetime.now(timezone.utc) - timedelta(hours=settings.PRICE_TTL_HOURS + 1)

    stale_row = LaborPrice(
        labor_service_id=service.id, source_id=src.id,
        price_min=Decimal("900"), price_avg=Decimal("999"), price_max=Decimal("1100"),
        updated_at=stale_at,
    )
    db_session.add(stale_row)
    db_session.commit()
    try:
        price = get_labor_price("Покраска стен", region=None)
        assert price is not None
        seed_src = db_session.query(PriceSource).filter(PriceSource.name == "seed").first()
        assert price.source_id == seed_src.id     # seed, не устаревший parser
        assert price.price_avg == Decimal("450")  # seed, не устаревшие 999
    finally:
        db_session.delete(stale_row)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_fresh_parser_price_is_returned(db_session):
    """Свежая parser-цена (моложе PRICE_TTL_HOURS) отдаётся, источник=parser (#167)."""
    service = db_session.query(LaborService).filter(LaborService.name == "Покраска стен").first()
    src = db_session.query(PriceSource).filter(PriceSource.name == "Мегастрой").first()
    fresh_at = datetime.now(timezone.utc) - timedelta(hours=1)

    fresh_row = LaborPrice(
        labor_service_id=service.id, source_id=src.id,
        price_min=Decimal("900"), price_avg=Decimal("999"), price_max=Decimal("1100"),
        updated_at=fresh_at,
    )
    db_session.add(fresh_row)
    db_session.commit()
    try:
        price = get_labor_price("Покраска стен", region=None)
        assert price is not None
        assert price.source_id == src.id          # источник — парсер
        assert price.price_avg == Decimal("999")  # не seed 450
    finally:
        db_session.delete(fresh_row)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_multiple_parser_sources_freshest_wins_deterministically(db_session):
    """Два не-seed источника (region IS NULL) с одинаковой вилкой, но разным updated_at:
    представитель — самый свежий, выбор детерминирован между прогонами (#167)."""
    service = db_session.query(LaborService).filter(LaborService.name == "Покраска стен").first()
    src_old = db_session.query(PriceSource).filter(PriceSource.name == "Мегастрой").first()
    src_new = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    now = datetime.now(timezone.utc)

    # Одинаковые цены → объединённая вилка совпадает, тай-брейк представителя
    # решает updated_at: побеждает самый свежий источник (src_new).
    row_old = LaborPrice(
        labor_service_id=service.id, source_id=src_old.id,
        price_min=Decimal("900"), price_avg=Decimal("1000"), price_max=Decimal("1100"),
        updated_at=now - timedelta(hours=5),
    )
    row_new = LaborPrice(
        labor_service_id=service.id, source_id=src_new.id,
        price_min=Decimal("900"), price_avg=Decimal("1000"), price_max=Decimal("1100"),
        updated_at=now - timedelta(hours=1),
    )
    db_session.add_all([row_old, row_new])
    db_session.commit()
    try:
        first = get_labor_price("Покраска стен", region=None)
        second = get_labor_price("Покраска стен", region=None)
        assert first is not None and second is not None
        assert first.source_id == src_new.id      # свежайший источник
        assert first.source_id == second.source_id  # детерминированно
        assert first.price_avg == Decimal("1000")
    finally:
        db_session.delete(row_old)
        db_session.delete(row_new)
        db_session.commit()
