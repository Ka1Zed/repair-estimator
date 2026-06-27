# app/tests/test_labor_parsers.py
# Региональные парсеры цен работ (#166): разбор сохранённого HTML-прайса (без сети),
# привязка цены к региону через update_labor_price, инвариант #159 (нулевую/мусорную
# цену не сохраняем, парсер не валит расчёт).

from decimal import Decimal
from pathlib import Path

import pytest

from app.db.models import LaborPrice, LaborService, PriceSource
from app.parsers.base import BaseParser, ParsedPrice
from app.parsers.garantstroikompleks_parser import GarantStroiParser
from app.parsers.labor_table_parser import _parse_price
from app.parsers.otdelka_spb_parser import OtdelkaSpbParser
from app.services.price_aggregator_service import get_labor_price, update_labor_price

FIXTURES = Path(__file__).parent / "fixtures"

# Услуги, которые должны находиться на обоих прайсах (вёрстка сохранена в фикстурах).
COMMON_SERVICES = [
    "Покраска стен",
    "Покраска потолка",
    "Шпаклевка стен",
    "Укладка ламината",
    "Укладка плитки",
    "Электромонтаж",
    "Сантехнические работы",
]

CASES = [
    (GarantStroiParser, "garantstroikompleks.html", "Москва", "garantstroikompleks.ru"),
    (OtdelkaSpbParser, "otdelka-spb.html", "Санкт-Петербург", "otdelka-spb.ru"),
]


def _parser_on_fixture(parser_cls, fixture_name):
    '''Парсер, читающий HTML из фикстуры вместо сети.'''
    parser = parser_cls()
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    parser._get_html = lambda: html
    return parser


# --- разбор HTML-прайса ---

@pytest.mark.parametrize("parser_cls,fixture,region,source", CASES)
def test_parser_metadata(parser_cls, fixture, region, source):
    parser = parser_cls()
    assert parser.region == region
    assert parser.source_name == source


@pytest.mark.parametrize("parser_cls,fixture,region,source", CASES)
@pytest.mark.parametrize("service", COMMON_SERVICES)
def test_parser_extracts_positive_prices(parser_cls, fixture, region, source, service):
    '''По каждой услуге парсер отдаёт валидную вилку min<=avg<=max, все > 0.'''
    parser = _parser_on_fixture(parser_cls, fixture)
    parsed = parser.fetch_price(service)
    assert isinstance(parsed, ParsedPrice)
    assert parsed.price_min > 0
    assert parsed.price_min <= parsed.price_avg <= parsed.price_max
    # Ссылка на прайс проставлена (для источника в смете).
    assert parsed.source_url == parser.PRICE_URL


def test_parser_unknown_service_raises():
    parser = _parser_on_fixture(GarantStroiParser, "garantstroikompleks.html")
    with pytest.raises(ValueError):
        parser.fetch_price("Нет такой услуги")


def test_parser_no_matching_rows_raises():
    '''Пустой прайс → RuntimeError; агрегатор поймает и уйдёт на seed (#159).'''
    parser = GarantStroiParser()
    parser._get_html = lambda: "<html><body><table></table></body></html>"
    with pytest.raises(RuntimeError):
        parser.fetch_price("Покраска стен")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("от 1 590 руб", Decimal(1590)),
        ("700/1100", Decimal(700)),
        ("350", Decimal(350)),
        ("по запросу", None),
        ("", None),
    ],
)
def test_parse_price(text, expected):
    assert _parse_price(text) == expected


# --- запись региональной цены через update_labor_price (#166) ---

class _FixtureParser(BaseParser):
    '''Парсер с фиксированной валидной ценой и заданным источником.'''
    source_name = "garantstroikompleks.ru"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        return ParsedPrice(
            price_min=Decimal("400"), price_avg=Decimal("500"), price_max=Decimal("600"),
            source_url="https://garantstroikompleks.ru/prajs-list",
        )


class _ZeroLaborParser(BaseParser):
    '''VPN/блок-страница: HTTP 200, но цена нулевая.'''
    source_name = "garantstroikompleks.ru"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        return ParsedPrice(price_min=Decimal(0), price_avg=Decimal(0), price_max=Decimal(0))


def _labor_row(db, service_name, source_name, region):
    service = db.query(LaborService).filter(LaborService.name == service_name).first()
    src = db.query(PriceSource).filter(PriceSource.name == source_name).first()
    return (
        db.query(LaborPrice)
        .filter(
            LaborPrice.labor_service_id == service.id,
            LaborPrice.source_id == src.id,
            LaborPrice.region == region,
        )
        .first()
    )


@pytest.mark.usefixtures("setup_test_db")
def test_update_labor_price_writes_region(db_session):
    '''update_labor_price(region=...) пишет цену с регионом и источником-сайтом.'''
    price = update_labor_price("Укладка плитки", parser=_FixtureParser(), region="Москва")
    try:
        assert price is not None
        assert price.region == "Москва"
        assert price.price_avg == Decimal("500")
        # Записано под источником-сайтом, не seed.
        row = _labor_row(db_session, "Укладка плитки", "garantstroikompleks.ru", "Москва")
        assert row is not None
        # И эту региональную цену предпочтёт lookup перед seed.
        looked_up = get_labor_price("Укладка плитки", region="Москва")
        assert looked_up.region == "Москва"
        assert looked_up.price_avg == Decimal("500")
    finally:
        db_session.query(LaborPrice).filter(
            LaborPrice.id == price.id
        ).delete()
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_update_labor_price_zero_not_persisted(db_session):
    '''Нулевая цена не сохраняется, расчёт уходит на seed (#159).'''
    assert _labor_row(db_session, "Укладка плитки", "garantstroikompleks.ru", "Москва") is None
    result = update_labor_price("Укладка плитки", parser=_ZeroLaborParser(), region="Москва")
    assert result is None
    assert _labor_row(db_session, "Укладка плитки", "garantstroikompleks.ru", "Москва") is None
