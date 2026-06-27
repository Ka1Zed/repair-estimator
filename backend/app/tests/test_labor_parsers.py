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
from app.parsers.prorabneva_parser import ProrabnevaParser
from app.parsers.remont_uroven_parser import RemontUrovenParser
from app.services.price_aggregator_service import get_labor_price, update_labor_price

FIXTURES = Path(__file__).parent / "fixtures"

# Услуги, которые должны находиться на каждом прайсе (вёрстка сохранена в фикстурах).
# prorabneva.ru не публикует шпаклёвку отдельной строкой — её closing закрывает otdelka.
SERVICES_BY_PARSER = {
    "garantstroikompleks.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                               "Укладка ламината", "Укладка плитки", "Электромонтаж",
                               "Сантехнические работы"],
    "remont-uroven.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                         "Укладка ламината", "Укладка плитки", "Электромонтаж",
                         "Сантехнические работы"],
    "otdelka-spb.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                       "Укладка ламината", "Укладка плитки", "Электромонтаж",
                       "Сантехнические работы"],
    "prorabneva.ru": ["Покраска стен", "Покраска потолка", "Укладка ламината",
                      "Укладка плитки", "Электромонтаж", "Сантехнические работы"],
}

CASES = [
    (GarantStroiParser, "garantstroikompleks.html", "Москва", "garantstroikompleks.ru"),
    (RemontUrovenParser, "remont-uroven.html", "Москва", "remont-uroven.ru"),
    (OtdelkaSpbParser, "otdelka-spb.html", "Санкт-Петербург", "otdelka-spb.ru"),
    (ProrabnevaParser, "prorabneva.html", "Санкт-Петербург", "prorabneva.ru"),
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
def test_parser_extracts_positive_prices(parser_cls, fixture, region, source):
    '''По каждой услуге парсер отдаёт валидную вилку min<=avg<=max, все > 0.'''
    parser = _parser_on_fixture(parser_cls, fixture)
    for service in SERVICES_BY_PARSER[source]:
        parsed = parser.fetch_price(service)
        assert isinstance(parsed, ParsedPrice), service
        assert parsed.price_min > 0, service
        assert parsed.price_min <= parsed.price_avg <= parsed.price_max, service
        # Ссылка на прайс проставлена (для источника в смете).
        assert parsed.source_url == parser.PRICE_URL, service


def test_unit_cell_not_parsed_as_price():
    '''Ячейка-единица «м2» (цифра 2) не должна стать ценой: берём цену >= MIN_PRICE.'''
    parser = ProrabnevaParser()
    parser._get_html = lambda: (
        "<html><body><table>"
        "<tr><td>Настил ламината</td><td>600 руб. 534 руб. м2</td>"
        "<td>600 руб. 534 руб.</td><td>м2</td></tr>"
        "</table></body></html>"
    )
    parsed = parser.fetch_price("Укладка ламината")
    assert parsed.price_min == Decimal(600)


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


# --- объединение цен нескольких сайтов одного региона (#166) ---

@pytest.mark.usefixtures("setup_test_db")
def test_labor_combines_multiple_regional_sites(db_session):
    '''
    Две parser-цены одного региона объединяются в одну вилку: min=минимум,
    max=максимум, avg=среднее средних. source — представительный сайт (его avg
    ближе к итоговому), sources — все сайты.
    '''
    service = db_session.query(LaborService).filter(LaborService.name == "Укладка плитки").first()
    garant = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    remont = db_session.query(PriceSource).filter(PriceSource.name == "remont-uroven.ru").first()
    rows = [
        LaborPrice(labor_service_id=service.id, source_id=garant.id, region="Москва",
                   price_min=Decimal("400"), price_avg=Decimal("1000"), price_max=Decimal("1300")),
        LaborPrice(labor_service_id=service.id, source_id=remont.id, region="Москва",
                   price_min=Decimal("1600"), price_avg=Decimal("2700"), price_max=Decimal("4500")),
    ]
    db_session.add_all(rows)
    db_session.commit()
    try:
        price = get_labor_price("Укладка плитки", region="Москва")
        assert price.price_min == Decimal("400")        # минимум по сайтам
        assert price.price_max == Decimal("4500")       # максимум по сайтам
        assert price.price_avg == Decimal("1850")       # среднее средних (1000+2700)/2
        assert price.region == "Москва"
        # Представительный сайт — garant (его avg 1000 ближе к 1850, чем 2700).
        assert price.source_id == garant.id
        assert price.source_url == rows[0].source_url
        assert set(price.contributing_sources) == {"garantstroikompleks.ru", "remont-uroven.ru"}
    finally:
        for r in rows:
            db_session.delete(r)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_single_site_reports_one_source(db_session):
    '''Один сайт на регион → вилка этого сайта, sources из одного элемента.'''
    service = db_session.query(LaborService).filter(LaborService.name == "Укладка плитки").first()
    garant = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    row = LaborPrice(labor_service_id=service.id, source_id=garant.id, region="Москва",
                     price_min=Decimal("400"), price_avg=Decimal("900"), price_max=Decimal("1300"))
    db_session.add(row)
    db_session.commit()
    try:
        price = get_labor_price("Укладка плитки", region="Москва")
        assert price.price_avg == Decimal("900")
        assert price.contributing_sources == ["garantstroikompleks.ru"]
    finally:
        db_session.delete(row)
        db_session.commit()
