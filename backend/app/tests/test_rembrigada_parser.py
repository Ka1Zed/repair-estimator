# app/tests/test_rembrigada_parser.py
# Парсер прайса rembrigada116.ru (company_price) на сохранённой вёрстке, без сети
# (по образцу региональных парсеров в test_labor_parsers.py). RembrigadaParser не
# ходит через _get_html, а дёргает requests.get внутри _load_rows — поэтому сеть
# глушим monkeypatch requests.get фикстурным HTML.

from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import rembrigada_parser
from app.parsers.rembrigada_parser import PRICE_URL, RembrigadaParser, _parse_price
from app.parsers.base import ParsedPrice

FIXTURES = Path(__file__).parent / "fixtures"

# Услуги, которые должны находиться на сохранённом прайсе.
SERVICES = [
    "Покраска стен",
    "Покраска потолка",
    "Шпаклевка стен",
    "Укладка ламината",
    "Укладка плитки",
    "Электромонтаж",
    "Сантехнические работы",
]


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture
def parser_on_fixture(monkeypatch):
    '''RembrigadaParser, читающий HTML из фикстуры вместо сети.'''
    html = (FIXTURES / "rembrigada.html").read_text(encoding="utf-8")
    monkeypatch.setattr(
        rembrigada_parser.requests, "get", lambda *a, **k: _FakeResponse(html)
    )
    return RembrigadaParser()


def test_parser_metadata():
    parser = RembrigadaParser()
    assert parser.source_name == "company_price"
    assert parser.region == "Казань"


@pytest.mark.parametrize("service", SERVICES)
def test_parser_extracts_positive_spread(parser_on_fixture, service):
    '''По каждой услуге парсер отдаёт валидную вилку min<=avg<=max, все > 0.'''
    parsed = parser_on_fixture.fetch_price(service)
    assert isinstance(parsed, ParsedPrice)
    assert parsed.price_min > 0
    assert parsed.price_min <= parsed.price_avg <= parsed.price_max
    # Ссылка на общий прайс проставлена (для источника в смете).
    assert parsed.source_url == PRICE_URL


def test_multiple_rows_combined_into_spread(parser_on_fixture):
    '''Две строки покраски стен (250 и 320) дают вилку по обеим, avg — среднее.'''
    parsed = parser_on_fixture.fetch_price("Покраска стен")
    assert parsed.price_min == Decimal(250)
    assert parsed.price_max == Decimal(320)
    assert parsed.price_avg == Decimal(285)  # round((250+320)/2)


def test_unknown_service_raises(parser_on_fixture):
    with pytest.raises(ValueError):
        parser_on_fixture.fetch_price("Нет такой услуги")


def test_no_matching_rows_raises(monkeypatch):
    '''Пустой прайс → RuntimeError; агрегатор поймает и уйдёт на seed (#159).'''
    monkeypatch.setattr(
        rembrigada_parser.requests,
        "get",
        lambda *a, **k: _FakeResponse("<html><body><table></table></body></html>"),
    )
    with pytest.raises(RuntimeError):
        RembrigadaParser().fetch_price("Покраска стен")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("от 1 590 руб", Decimal(1590)),
        ("1 100 руб", Decimal(1100)),
        ("350", Decimal(350)),
        ("по запросу", None),
        ("", None),
    ],
)
def test_parse_price(text, expected):
    assert _parse_price(text) == expected
