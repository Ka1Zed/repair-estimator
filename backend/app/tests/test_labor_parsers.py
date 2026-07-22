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
from app.parsers.kaz_stroyka_parser import KazStroykaParser
from app.parsers._stats import filter_outliers
from app.parsers.labor_table_parser import (
    LABOR_SERVICE_MAP,
    _matches,
    _normalize_unit,
    _parse_price,
    _unit_matches,
)
from app.parsers.otdelka_spb_parser import OtdelkaSpbParser
from app.parsers.prorabneva_parser import ProrabnevaParser
from app.parsers.remont_uroven_parser import RemontUrovenParser
from app.services.price_aggregator_service import get_labor_price, update_labor_price

FIXTURES = Path(__file__).parent / "fixtures"

# Услуги, которые должны находиться на каждом прайсе (вёрстка сохранена в фикстурах).
# prorabneva.ru не публикует шпаклёвку отдельной строкой — её closing закрывает otdelka.
# Демонтаж/сантехника (#401) — не на каждом прайсе поделены на все подуслуги
# (у части сайтов, напр. otdelka-spb.ru, нет отдельно бачка унитаза или демонтажа
# стяжки строкой) — список per-parser отражает реальную вёрстку фикстуры, а не
# требует полного покрытия (недостающее уходит в seed-fallback, #159).
SERVICES_BY_PARSER = {
    "garantstroikompleks.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                               "Укладка ламината", "Укладка плитки", "Электромонтаж",
                               "Демонтаж напольного покрытия", "Демонтаж стен и перегородок",
                               "Демонтаж стяжки", "Установка смесителя", "Установка унитаза",
                               "Установка бачка унитаза",
                               "Штробление", "Грунтование потолка", "Шпаклевка потолка"],
    "remont-uroven.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                         "Укладка ламината", "Укладка плитки", "Электромонтаж",
                         "Демонтаж напольного покрытия", "Демонтаж стен и перегородок",
                         "Демонтаж стяжки", "Установка смесителя", "Установка унитаза",
                         "Штробление", "Грунтование потолка", "Шпаклевка потолка",
                         "Закладная под светильник"],
    "otdelka-spb.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                       "Укладка ламината", "Укладка плитки", "Электромонтаж",
                       "Демонтаж напольного покрытия", "Установка смесителя",
                       "Установка унитаза",
                       "Штробление", "Грунтование потолка", "Шпаклевка потолка",
                       "Ниша под карниз"],
    "prorabneva.ru": ["Покраска стен", "Покраска потолка", "Укладка ламината",
                      "Укладка плитки", "Электромонтаж", "Демонтаж напольного покрытия",
                      "Демонтаж стен и перегородок", "Демонтаж стяжки",
                      "Установка смесителя", "Установка унитаза",
                      "Штробление", "Грунтование потолка", "Ниша под карниз",
                      "Закладная под светильник"],
    "kaz-stroyka.ru": ["Покраска стен", "Покраска потолка", "Шпаклевка стен",
                       "Укладка ламината", "Укладка плитки", "Электромонтаж",
                       "Демонтаж напольного покрытия", "Демонтаж стен и перегородок",
                       "Демонтаж стяжки", "Установка смесителя", "Установка унитаза",
                       "Установка бачка унитаза",
                       "Штробление", "Грунтование потолка", "Шпаклевка потолка",
                       "Ниша под карниз", "Закладная под светильник"],
}

# Фикстура — имя файла (прайс на одной странице) либо словарь url -> файл
# (kaz-stroyka.ru публикует отделку, электрику и сантехнику отдельными страницами).
KAZ_STROYKA_FIXTURES = {
    KazStroykaParser.PRICE_URL: "kaz-stroyka-otdelka.html",
    KazStroykaParser.EXTRA_PAGE_URLS[0]: "kaz-stroyka-elektrika.html",
    KazStroykaParser.EXTRA_PAGE_URLS[1]: "kaz-stroyka-santekhnika.html",
}

CASES = [
    (GarantStroiParser, "garantstroikompleks.html", "Москва", "garantstroikompleks.ru"),
    (RemontUrovenParser, "remont-uroven.html", "Москва", "remont-uroven.ru"),
    (OtdelkaSpbParser, "otdelka-spb.html", "Санкт-Петербург", "otdelka-spb.ru"),
    (ProrabnevaParser, "prorabneva.html", "Санкт-Петербург", "prorabneva.ru"),
    (KazStroykaParser, KAZ_STROYKA_FIXTURES, "Казань", "kaz-stroyka.ru"),
]


def _parser_on_fixture(parser_cls, fixture):
    '''Парсер, читающий HTML из фикстуры вместо сети.'''
    parser = parser_cls()
    if isinstance(fixture, str):
        fixture = {parser.PRICE_URL: fixture}
    files = {url: FIXTURES / name for url, name in fixture.items()}
    parser._get_html = lambda url: files[url].read_text(encoding="utf-8")
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
        # Ссылка на прайс проставлена (для источника в смете) и ведёт на одну
        # из страниц прайса этого сайта.
        assert parsed.source_url in parser._page_urls(), service


# Нишевые услуги (#407): раньше жили только на seed-цене. После роутинга в прайсы
# подрядчиков у каждой должно набираться >=3 источника (без учёта seed), чтобы вилка
# min/avg/max опиралась на рынок, а не на один захардкоженный коридор.
THIN_SERVICES_MIN_SOURCES = {
    "Штробление": 3,
    "Грунтование потолка": 3,
    "Шпаклевка потолка": 3,
    "Ниша под карниз": 3,
    "Закладная под светильник": 3,
}


@pytest.mark.parametrize("service,min_sources", THIN_SERVICES_MIN_SOURCES.items())
def test_thin_labor_services_have_price_corridor(service, min_sources):
    '''#407: услуга находится минимум на min_sources прайсах подрядчиков.'''
    hits = 0
    for parser_cls, fixture, _region, _source in CASES:
        parser = _parser_on_fixture(parser_cls, fixture)
        try:
            parser.fetch_price(service)
        except RuntimeError:
            continue  # на этом прайсе услуги нет -> уйдёт в seed-fallback
        hits += 1
    assert hits >= min_sources, f"{service}: источников {hits} < {min_sources}"


def test_unit_cell_not_parsed_as_price():
    '''Ячейка-единица «м2» (цифра 2) не должна стать ценой: берём цену >= MIN_PRICE.'''
    parser = ProrabnevaParser()
    parser._get_html = lambda url: (
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
    parser._get_html = lambda url: "<html><body><table></table></body></html>"
    with pytest.raises(RuntimeError):
        parser.fetch_price("Покраска стен")


# --- многостраничный прайс (kaz-stroyka.ru: отделка/электрика/сантехника) ---

def test_multipage_source_url_points_to_service_page():
    '''source_url ведёт на страницу, где услуга опубликована, а не на общий прайс.'''
    parser = _parser_on_fixture(KazStroykaParser, KAZ_STROYKA_FIXTURES)
    assert parser.fetch_price("Покраска стен").source_url == KazStroykaParser.PRICE_URL
    assert (parser.fetch_price("Электромонтаж").source_url
            == KazStroykaParser.EXTRA_PAGE_URLS[0])
    assert (parser.fetch_price("Установка смесителя").source_url
            == KazStroykaParser.EXTRA_PAGE_URLS[1])


def test_multipage_unavailable_page_does_not_break_others():
    '''Недоступная страница отделки не роняет услуги с других страниц (#159):
    электрика/сантехника парсятся, отделочные услуги — RuntimeError -> seed.'''
    import requests

    files = {url: FIXTURES / name for url, name in KAZ_STROYKA_FIXTURES.items()}

    def get_html(url):
        if url == KazStroykaParser.PRICE_URL:
            raise requests.ConnectionError("страница недоступна")
        return files[url].read_text(encoding="utf-8")

    parser = KazStroykaParser()
    parser._get_html = get_html
    assert parser.fetch_price("Электромонтаж").price_min > 0
    assert parser.fetch_price("Установка смесителя").price_min > 0
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


# --- отсев ценовых выбросов методом Тьюки (#242) ---

def _D(*xs):
    return [Decimal(x) for x in xs]


def test_filter_outliers_drops_high_outlier():
    '''Дорогая нишевая работа отсекается — вилка считается по «телу» выборки.'''
    prices = _D(400, 450, 500, 520, 550, 580, 600, 650, 7000)
    filtered = filter_outliers(prices)
    assert Decimal(7000) not in filtered
    assert max(filtered) < Decimal(7000)


def test_filter_outliers_drops_outlier_on_issue_sample():
    '''Пример из #242 [400, 500, 550, 600, 7000] (5 строк) — выброс отсекается.'''
    prices = _D(400, 500, 550, 600, 7000)
    filtered = filter_outliers(prices)
    assert Decimal(7000) not in filtered
    assert filtered == _D(400, 500, 550, 600)


def test_filter_outliers_keeps_small_sample():
    '''На выборке < 4 квартили не считаем — оставляем всё как есть.'''
    prices = _D(400, 500, 7000)
    assert filter_outliers(prices) == prices


def test_filter_outliers_degenerate_all_equal():
    '''Все цены равны (iqr=0) → фильтр не должен обнулить выборку.'''
    prices = _D(500, 500, 500, 500)
    assert filter_outliers(prices) == prices


def test_filter_outliers_with_key_preserves_url():
    '''key достаёт цену из пары (цена, url); отфильтрованные пары сохраняют url.'''
    items = [(p, "u") for p in _D(400, 450, 500, 520, 550, 580, 600, 650, 7000)]
    filtered = filter_outliers(items, key=lambda it: it[0])
    assert (Decimal(7000), "u") not in filtered
    assert all(url == "u" for _, url in filtered)


def _rows_html(service_rows: list[tuple[str, int]]) -> str:
    cells = "".join(
        f"<tr><td>{name}</td><td>{price} руб</td></tr>" for name, price in service_rows
    )
    return f"<html><body><table>{cells}</table></body></html>"


def test_fetch_price_excludes_outlier_from_spread():
    '''Прайс с явным выбросом по услуге → price_max не выброс, вилка по телу.'''
    rows = [(f"Установка розетки №{i}", p)
            for i, p in enumerate([400, 450, 500, 520, 550, 580, 600, 650, 7000])]
    parser = GarantStroiParser()
    parser._get_html = lambda url: _rows_html(rows)
    parsed = parser.fetch_price("Электромонтаж")
    assert parsed.price_max < Decimal(7000)
    assert parsed.price_min == Decimal(400)
    # Ссылка на источник по-прежнему проставлена (из отфильтрованного набора).
    assert parsed.source_url in parser._page_urls()


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
    price = update_labor_price("Укладка плитки", parser=_FixtureParser(), db=db_session, region="Москва")
    try:
        assert price is not None
        assert price.region == "Москва"
        assert price.price_avg == Decimal("500")
        # Записано под источником-сайтом, не seed.
        row = _labor_row(db_session, "Укладка плитки", "garantstroikompleks.ru", "Москва")
        assert row is not None
        # И эту региональную цену предпочтёт lookup перед seed.
        looked_up = get_labor_price("Укладка плитки", db=db_session, region="Москва")
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
    result = update_labor_price("Укладка плитки", parser=_ZeroLaborParser(), db=db_session, region="Москва")
    assert result is None
    assert _labor_row(db_session, "Укладка плитки", "garantstroikompleks.ru", "Москва") is None


# --- объединение цен нескольких сайтов одного региона (#166) ---

@pytest.mark.usefixtures("setup_test_db")
def test_labor_combines_multiple_regional_sites(db_session):
    '''
    Две parser-цены одного региона объединяются в одну вилку: min=минимум,
    max=максимум, avg=среднее средних. source — представительный сайт (его avg
    ближе к итоговому), sources — все сайты. Band каждого сайта узкий (в своём
    коридоре, #411) → не клампится, реальная межсайтовая дисперсия проходит.
    '''
    service = db_session.query(LaborService).filter(LaborService.name == "Укладка плитки").first()
    garant = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    remont = db_session.query(PriceSource).filter(PriceSource.name == "remont-uroven.ru").first()
    rows = [
        LaborPrice(labor_service_id=service.id, source_id=garant.id, region="Москва",
                   price_min=Decimal("900"), price_avg=Decimal("1000"), price_max=Decimal("1150"),
                   source_url="https://garantstroikompleks.ru/prajs-list"),
        LaborPrice(labor_service_id=service.id, source_id=remont.id, region="Москва",
                   price_min=Decimal("2400"), price_avg=Decimal("2700"), price_max=Decimal("3200"),
                   source_url="https://remont-uroven.ru/price.html"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    try:
        price = get_labor_price("Укладка плитки", db=db_session, region="Москва")
        assert price.price_min == Decimal("900")        # минимум по сайтам (garant), не клампнут
        assert price.price_max == Decimal("3200")       # максимум по сайтам (remont), не клампнут
        assert price.price_avg == Decimal("1850")       # среднее средних (1000+2700)/2
        assert price.region == "Москва"
        # Представительный сайт — garant (его avg 1000 ближе к 1850, чем 2700).
        assert price.source_id == garant.id
        assert price.source_url == rows[0].source_url
        assert set(price.contributing_sources) == {"garantstroikompleks.ru", "remont-uroven.ru"}
        # #348: garant дал ещё и price_min → он же представитель, отдельную ссылку
        # не дублируем (null). price_max дал remont → его источник/ссылка видны отдельно.
        assert price.min_source_id is None
        assert price.min_source_url is None
        assert price.max_source_id == remont.id
        assert price.max_source_url == rows[1].source_url
    finally:
        for r in rows:
            db_session.delete(r)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_combine_attributes_min_and_max_to_different_sources_than_representative(db_session):
    '''
    #348: когда ни минимум, ни максимум вилки не пришёлся на представителя —
    обе границы должны сослаться на СВОИ сайты (разные ссылки), а не молчать/
    дублировать source_url представителя. Границы дают дешёвый и дорогой сайты
    с узкими band'ами (не клампнуты, #411) → атрибутируются к своим источникам.
    '''
    service = db_session.query(LaborService).filter(LaborService.name == "Укладка плитки").first()
    garant = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    remont = db_session.query(PriceSource).filter(PriceSource.name == "remont-uroven.ru").first()
    otdelka = db_session.query(PriceSource).filter(PriceSource.name == "otdelka-spb.ru").first()
    rows = [
        LaborPrice(labor_service_id=service.id, source_id=garant.id, region="Москва",
                   price_min=Decimal("950"), price_avg=Decimal("1000"), price_max=Decimal("1100"),
                   source_url="https://garantstroikompleks.ru/prajs-list"),
        LaborPrice(labor_service_id=service.id, source_id=remont.id, region="Москва",
                   price_min=Decimal("2400"), price_avg=Decimal("2700"), price_max=Decimal("3100"),
                   source_url="https://remont-uroven.ru/price.html"),
        LaborPrice(labor_service_id=service.id, source_id=otdelka.id, region="Москва",
                   price_min=Decimal("90"), price_avg=Decimal("100"), price_max=Decimal("110"),
                   source_url="https://otdelka-spb.ru/prajjs/"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    try:
        price = get_labor_price("Укладка плитки", db=db_session, region="Москва")
        assert price.price_min == Decimal("90")     # минимум — otdelka (не клампнут)
        assert price.price_max == Decimal("3100")   # максимум — remont (не клампнут)
        # Представитель — garant (avg 1000 ближе к объединённой 1267, чем 2700 и 100).
        assert price.source_id == garant.id
        assert price.min_source_id == otdelka.id
        assert price.min_source_url == rows[2].source_url
        assert price.max_source_id == remont.id
        assert price.max_source_url == rows[1].source_url
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
        price = get_labor_price("Укладка плитки", db=db_session, region="Москва")
        assert price.price_avg == Decimal("900")
        assert price.contributing_sources == ["garantstroikompleks.ru"]
    finally:
        db_session.delete(row)
        db_session.commit()


@pytest.mark.usefixtures("setup_test_db")
def test_labor_flat_premium_source_does_not_drag_avg(db_session):
    '''
    #412: сайт с реальным распределением (терции 600..3000, avg 1200) + одиночный
    плоский премиум-прайс 3300. avg объединённой вилки тяготеет к телу распределения
    (1200), а НЕ к среднему средних ((1200+3300)/2=2250): плоский подрядчик влияет
    только на верхнюю границу вилки, но не тянет центр. Воспроизводит перекос из
    живой сверки #407 («Шпаклевка потолка», Казань).
    '''
    service = db_session.query(LaborService).filter(LaborService.name == "Укладка плитки").first()
    garant = db_session.query(PriceSource).filter(PriceSource.name == "garantstroikompleks.ru").first()
    remont = db_session.query(PriceSource).filter(PriceSource.name == "remont-uroven.ru").first()
    rows = [
        LaborPrice(labor_service_id=service.id, source_id=garant.id, region="Москва",
                   price_min=Decimal("600"), price_avg=Decimal("1200"), price_max=Decimal("3000"),
                   source_url="https://garantstroikompleks.ru/prajs-list"),
        LaborPrice(labor_service_id=service.id, source_id=remont.id, region="Москва",
                   price_min=Decimal("3300"), price_avg=Decimal("3300"), price_max=Decimal("3300"),
                   source_url="https://remont-uroven.ru/price.html"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    try:
        price = get_labor_price("Укладка плитки", db=db_session, region="Москва")
        # Центр — по неплоскому сайту (1200), а не среднее средних (2250).
        assert price.price_avg == Decimal("1200")
        # Плоский сайт по-прежнему задаёт верхнюю границу вилки.
        assert price.price_max == Decimal("3300")
        assert set(price.contributing_sources) == {"garantstroikompleks.ru", "remont-uroven.ru"}
    finally:
        for r in rows:
            db_session.delete(r)
        db_session.commit()


# --- контекстный матчинг: единица измерения и отсев дельт (#391) ---

@pytest.mark.parametrize(
    "text,expected",
    [
        ("м2", "м²"), ("м 2", "м²"), ("кв.м.", "м²"), ("м²", "м²"),
        ("м3", "м³"), ("куб.м", "м³"),
        ("п.м.", "м"), ("пог.м.", "м"), ("мп", "м"), ("м/п", "м"), ("м", "м"),
        ("шт", "шт"), ("шт.", "шт"), ("компл", "шт"),
        ("точка", "точка"),
        ("Покраска стен", None), ("", None),
    ],
)
def test_normalize_unit(text, expected):
    assert _normalize_unit(text) == expected


@pytest.mark.parametrize(
    "row_unit,expected_unit,expected_match",
    [
        (None, "м²", True),     # единицу не распознали -> не отсеиваем (подстраховка)
        ("м²", "м²", True),
        ("м³", "м²", False),    # объём не сопоставим с площадью (#391)
        ("шт", "точка", True),  # сайты пишут "шт" там, где у нас каталожная "точка"
        ("точка", "шт", True),
        ("м", "м²", False),
    ],
)
def test_unit_matches(row_unit, expected_unit, expected_match):
    assert _unit_matches(row_unit, expected_unit) is expected_match


def test_matches_rejects_addon_surcharge_rows():
    '''«... (дополнительно к стоимости ...)» — доплата к другой строке прайса,
    а не цена самостоятельной операции (prorabneva.ru, #391).'''
    rule = LABOR_SERVICE_MAP["Укладка плитки"]
    assert not _matches(
        "облицовка стен кафельной плиткой по диагонали (дополнительно к стоимости "
        "облицовки кафельной плитки одного рисунка)", rule,
    )
    assert _matches("облицовка стен каф.плиткой", rule)


def test_wall_leveling_excludes_removal_row():
    '''«Выравнивание стен» — нанесение/выравнивание, а не снятие старой штукатурки
    (otdelka-spb.ru: «отбивка штукатурки со стен», #391).'''
    rule = LABOR_SERVICE_MAP["Выравнивание стен"]
    assert not _matches("отбивка штукатурки со стен", rule)
    assert _matches("штукатурка стен по маякам", rule)


def test_electrical_install_excludes_switchboard_row():
    '''«Электромонтаж» — розетка/выключатель «за точку», а не монтаж/установка
    электрощита (otdelka-spb.ru, #391): старое слово "электрощит" не матчилось
    реальной формулировке "электрического щита".'''
    rule = LABOR_SERVICE_MAP["Электромонтаж"]
    assert not _matches(
        "установка электрического щита под электроавтоматы на 24 модулей врезка в бетон",
        rule,
    )
    assert _matches("установка розетки", rule)


def test_priming_excludes_bundled_waterproofing_row():
    '''«Грунтование» — не составная строка с чужой услугой: для гидроизоляции есть
    отдельная услуга «Гидроизоляция» (otdelka-spb.ru, #391).'''
    rule = LABOR_SERVICE_MAP["Грунтование"]
    assert not _matches("устройство гидроизоляции пола/грунтовка пола/обеспыливание", rule)
    assert _matches("грунтовка стен", rule)


def test_demolition_excludes_per_item_and_volume_rows_on_fixture():
    '''«Демонтаж стен и перегородок» — услуга за м²; штучные (шт) и объёмные (м³)
    строки прайса не сопоставимы по цене с площадью и не должны попадать в вилку
    (#391). На фикстуре без фильтра по единице price_max доходил до 8500 ₽
    («разборка монолитных бетонных конструкций», м³) — заведомо не то же самое,
    что демонтаж кирпичной стены (м²).'''
    parser = _parser_on_fixture(GarantStroiParser, "garantstroikompleks.html")
    parsed = parser.fetch_price("Демонтаж стен и перегородок")
    assert parsed.price_max < Decimal(8500)


def test_demolition_splits_floor_covering_from_structural_walls_on_fixture():
    '''«Демонтаж напольного покрытия» (линолеум/ламинат) и «Демонтаж стен и
    перегородок» (кирпич/бетон) — разные подвыборки с разным порядком цен (#401):
    раньше одна услуга «Демонтаж» держала оба конца на одной вилке (×10-40).'''
    parser = _parser_on_fixture(GarantStroiParser, "garantstroikompleks.html")
    floor_covering = parser.fetch_price("Демонтаж напольного покрытия")
    walls = parser.fetch_price("Демонтаж стен и перегородок")
    assert floor_covering.price_avg < walls.price_avg


def test_plumbing_splits_faucet_toilet_and_tank_on_fixture():
    '''«Установка бачка унитаза», «Установка смесителя», «Установка унитаза» —
    разные операции по объёму работы (#401): раньше все три были одной услугой
    «Сантехнические работы» на одной вилке.'''
    parser = _parser_on_fixture(GarantStroiParser, "garantstroikompleks.html")
    tank = parser.fetch_price("Установка бачка унитаза")
    faucet = parser.fetch_price("Установка смесителя")
    toilet = parser.fetch_price("Установка унитаза")
    assert tank.price_avg < faucet.price_avg < toilet.price_avg


def test_electrical_install_narrows_spread_on_fixture():
    '''На otdelka-spb.ru «Электромонтаж» без фильтра включал ~20 строк монтажа
    электрощита (400-8500 ₽) — вилка сужается после их исключения (#391).'''
    parser = _parser_on_fixture(OtdelkaSpbParser, "otdelka-spb.html")
    parsed = parser.fetch_price("Электромонтаж")
    assert parsed.price_max < Decimal(2000)


class TestRoughWorksRouting:
    """Черновые строки прайса роутятся в отдельные услуги, а не выкидываются (#190)."""

    def test_rough_rows_match_their_services(self):
        """Демонтаж/выравнивание/стяжка/гидроизоляция/грунт находят свою услугу."""
        cases = {
            "Демонтаж перегородки": "Демонтаж стен и перегородок",
            "Выравнивание стен штукатуркой": "Выравнивание стен",
            "Устройство стяжки пола": "Стяжка пола",
            "Гидроизоляция пола санузла": "Гидроизоляция",
            "Грунтование стен": "Грунтование",
        }
        for row_name, service in cases.items():
            assert _matches(row_name.lower(), LABOR_SERVICE_MAP[service]), \
                f"строка «{row_name}» не попала в услугу «{service}»"

    def test_finish_services_still_exclude_rough(self):
        """Финишные услуги по-прежнему исключают черновые строки — цена финиша не засоряется."""
        assert not _matches("демонтаж старой краски со стен", LABOR_SERVICE_MAP["Покраска стен"])
        assert not _matches("выравнивание стен штукатуркой", LABOR_SERVICE_MAP["Покраска стен"])
        assert not _matches("грунтование стен", LABOR_SERVICE_MAP["Покраска стен"])
        # А чистая покраска стен в свою услугу попадает.
        assert _matches("покраска стен в два слоя", LABOR_SERVICE_MAP["Покраска стен"])
