# app/tests/test_megastroy_parser.py
# Разбор HTML каталога Мегастроя без сети (#197, #277): парсер материалов отдаёт
# source_url конкретной карточки товара (та, чья цена ближе к показанной avg), при
# отсутствии ссылки деградирует до URL категории, а для категорий с несколькими
# витринными единицами (замазка/добавки затесались в шпаклёвку/затирку) отсекает
# позиции с чужой единицей. Сетевой смоук — в test_live_parsers.py.

from decimal import Decimal

import pytest

from app.parsers import megastroy_parser
from app.parsers._stats import filter_outliers
from app.parsers.megastroy_parser import (
    CATEGORY_MAP,
    MegastroyParser,
    _build_headers,
    _length_m_from_title,
    _parse_page,
    _site_unit,
)

PAINT_URL = CATEGORY_MAP["Краска для стен"].urls[0]


def _item(price: str, href: str | None) -> str:
    # Карточка Мегастроя: первыми идут кнопки-заглушки с href="javascript:"
    # (сравнить/избранное), реальная ссылка на товар — .js-search-product-link.
    # Без блока цены/названия — эти тесты про краску (site_unit=None, фильтр не идёт).
    link = f'<a class="js-search-product-link" href="{href}">товар</a>' if href else ""
    return (
        '<div class="products-list__item">'
        '<a class="js-compare-product" href="javascript:"></a>'
        '<a class="js-favorite" href="javascript:"></a>'
        f"{link}"
        f'<meta itemprop="price" content="{price}">'
        "</div>"
    )


def _priced_item(price: str, unit: str, title: str = "", href: str | None = "/products/1") -> str:
    # Полная карточка — с названием и текстом витринной единицы рядом с ценой,
    # как её реально пишет Мегастрой ("179 ₽/шт").
    link = f'<a class="js-search-product-link" href="{href}">товар</a>' if href else ""
    return (
        '<div class="products-list__item">'
        '<div class="products-list__content-title">'
        f'<a href="{href or "#"}" title="{title}">{title}</a>'
        "</div>"
        '<div class="products-price">'
        '<div class="products-price__value" itemprop="offers">'
        f"{price} ₽/{unit}"
        f'<meta content="{price}" itemprop="price">'
        "</div></div>"
        f"{link}"
        "</div>"
    )


def _page(*items: str) -> str:
    return "<html><body>" + "".join(items) + "</body></html>"


def test_parse_page_returns_price_and_absolute_url():
    html = _page(
        _item("150", "/catalog/kraski-dlya-vnutrennih-rabot/kraska-a"),
        _item("250", "https://kazan.megastroy.com/catalog/x/kraska-b"),
    )
    items = _parse_page(html, PAINT_URL)
    assert [(p, u) for p, u, _unit, _title in items] == [
        (Decimal("150"), "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot/kraska-a"),
        (Decimal("250"), "https://kazan.megastroy.com/catalog/x/kraska-b"),
    ]


def test_parse_page_skips_items_without_price():
    html = _page(_item("0", "/catalog/x/free"), _item("100", "/catalog/x/ok"))
    items = _parse_page(html, PAINT_URL)
    assert [(p, u) for p, u, _unit, _title in items] == [(Decimal("100"), "https://kazan.megastroy.com/catalog/x/ok")]


def test_parse_page_extracts_site_unit_and_title():
    html = _page(_priced_item("179", "шт", "Замазка строительная универсальная 1,4кг ведро"))
    price, url, unit, title = _parse_page(html, PAINT_URL)[0]
    assert price == Decimal("179")
    assert url == "https://kazan.megastroy.com/products/1"
    assert unit == "шт"
    assert title == "Замазка строительная универсальная 1,4кг ведро"


def test_site_unit_parses_known_aliases():
    assert _site_unit("179 ₽/шт") == "шт"
    assert _site_unit("399 ₽/м2") == "м²"
    assert _site_unit("1 295 ₽/рул") == "рулон"
    assert _site_unit("20 ₽/кг") == "кг"
    assert _site_unit("нет цены рядом") is None


def test_length_from_title_takes_largest_dimension():
    # Плинтус: "72х2500мм" — сечение 72мм, рейка 2500мм → 2.5 м.
    assert _length_m_from_title("Плинтус напольный ПВХ Lima 72х2500мм Белый") == Decimal("2.5")


def test_length_from_title_handles_triple_dimension():
    assert _length_m_from_title("Ламинат Egger Дуб Гихон светлый 1292х193х7мм 31кл") == Decimal("1.292")


def test_length_from_title_missing_dimension_returns_none():
    assert _length_m_from_title("Товар без размеров в названии") is None


def _patch_pages(monkeypatch, page_html: str):
    '''Первая страница каталога отдаёт page_html, со 2-й — 404 (конец пагинации).'''

    class FakeResponse:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_get(url, **kwargs):
        return FakeResponse(page_html) if "page=" not in url else FakeResponse("", 404)

    monkeypatch.setattr(megastroy_parser.requests, "get", fake_get)
    monkeypatch.setattr(megastroy_parser.time, "sleep", lambda *a, **k: None)


def test_source_url_points_to_product_closest_to_avg(monkeypatch):
    # Цены 100/200/300 → avg=200 → представитель — карточка за 200.
    html = _page(
        _item("100", "/catalog/x/kraska-a"),
        _item("200", "/catalog/x/kraska-b"),
        _item("300", "/catalog/x/kraska-c"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("200")
    assert parsed.source_url == "https://kazan.megastroy.com/catalog/x/kraska-b"


def test_source_url_falls_back_to_category_when_no_link(monkeypatch):
    # У товара-представителя нет ссылки → деградируем до URL категории, не падаем.
    html = _page(_item("199", None))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed.source_url == PAINT_URL


def _items(*prices: str) -> list[tuple[Decimal, str | None]]:
    return [(Decimal(p), f"/catalog/x/{p}") for p in prices]


def test_filter_outliers_drops_high_designer_paint():
    # Бытовые интерьерные краски в узкой полосе + один дизайнерский выброс 14999.
    items = _items("175", "200", "210", "220", "230", "250", "14999")
    filtered = filter_outliers(items, key=lambda it: it[0])
    prices = [p for p, _ in filtered]
    assert Decimal("14999") not in prices
    assert max(prices) / min(prices) < 4  # вилка сузилась с ~85× до разумной


def test_filter_outliers_keeps_small_sample():
    # На выборке < 4 квартили бессмысленны — ничего не отсекаем.
    items = _items("100", "9000", "14999")
    assert filter_outliers(items, key=lambda it: it[0]) == items


def test_filter_outliers_keeps_equal_prices():
    # Все цены равны → IQR=0 → отсекать нечего, выборка не должна опустеть.
    items = _items("250", "250", "250", "250")
    assert filter_outliers(items, key=lambda it: it[0]) == items


def test_fetch_price_excludes_outliers_from_spread_and_source(monkeypatch):
    # Выброс 14999 не должен попасть ни в max, ни в товар-представитель (#197).
    html = _page(
        _item("175", "/catalog/x/grunt"),
        _item("200", "/catalog/x/kraska-a"),
        _item("210", "/catalog/x/kraska-b"),
        _item("220", "/catalog/x/kraska-c"),
        _item("230", "/catalog/x/kraska-d"),
        _item("250", "/catalog/x/kraska-e"),
        _item("14999", "/catalog/x/designer"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed.price_max == Decimal("250")
    assert parsed.price_max / parsed.price_min < 4
    assert "designer" not in (parsed.source_url or "")


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        MegastroyParser().fetch_price("Нет такого материала")


# Фильтр по витринной единице (#277): категория "Шпаклевка" мешает мешковый товар
# (кг) с "замазкой" в ведре (шт) — берём только совпадающую с материалом единицу.


def test_putty_category_drops_items_priced_per_piece(monkeypatch):
    html = _page(
        _priced_item("30", "кг", "Шпаклевка ЕК К300 20 кг", href="/products/putty"),
        _priced_item("179", "шт", "Замазка строительная универсальная 1,4кг ведро", href="/products/zamazka"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка финишная")

    assert parsed.price_avg == Decimal("30")
    assert "zamazka" not in (parsed.source_url or "")


def test_material_without_matching_unit_raises(monkeypatch):
    # Ни одна позиция не подошла по единице → RuntimeError → агрегатор уйдёт в seed.
    html = _page(_priced_item("179", "шт", "Замазка строительная", href="/products/zamazka"))
    _patch_pages(monkeypatch, html)

    with pytest.raises(RuntimeError):
        MegastroyParser().fetch_price("Шпаклевка стартовая")


# Плинтус (#277): витринная единица — "шт" (рейка фиксированной длины), наша
# база — метр; цену приводим делением на длину рейки из названия.


def test_plintus_normalizes_price_per_piece_to_price_per_meter(monkeypatch):
    html = _page(
        _priced_item(
            "560", "шт", "Плинтус напольный ПВХ Lima 72х2500мм Белый", href="/products/plintus-a"
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("224")  # 560 / 2.5 м


def test_plintus_skips_items_without_parsable_length(monkeypatch):
    html = _page(
        _priced_item("560", "шт", "Плинтус напольный ПВХ Lima 72х2500мм Белый", href="/products/ok"),
        _priced_item("400", "шт", "Плинтус без размера в названии", href="/products/no-size"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("224")
    assert "no-size" not in (parsed.source_url or "")


# Плитка (#277): размазана по двум категориям Мегастроя — керамогранит и
# керамическая плитка, — обе должны попасть в общую выборку.


def test_tile_combines_two_categories(monkeypatch):
    granit_html = _page(_priced_item("1000", "м2", "Керамогранит А", href="/products/granit"))
    keramika_html = _page(_priced_item("1200", "м2", "Плитка керамическая Б", href="/products/keramika"))

    class FakeResponse:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_get(url, **kwargs):
        if "page=" in url:
            return FakeResponse("", 404)
        if "keramogranit" in url:
            return FakeResponse(granit_html)
        if "keramicheskaya-plitka" in url:
            return FakeResponse(keramika_html)
        return FakeResponse("", 404)

    monkeypatch.setattr(megastroy_parser.requests, "get", fake_get)
    monkeypatch.setattr(megastroy_parser.time, "sleep", lambda *a, **k: None)

    parsed = MegastroyParser().fetch_price("Плитка")

    assert parsed.price_min == Decimal("1000")
    assert parsed.price_max == Decimal("1200")


# _build_headers: приоритет MEGASTROY_COOKIE (ручной hand-off) над
# MEGASTROY_HEADLESS (beta-харвестер).


def test_build_headers_no_cookie_by_default(monkeypatch):
    monkeypatch.delenv("MEGASTROY_COOKIE", raising=False)
    monkeypatch.setattr(megastroy_parser.settings, "MEGASTROY_HEADLESS", False)

    headers = _build_headers()

    assert "Cookie" not in headers


def test_build_headers_uses_manual_cookie(monkeypatch):
    monkeypatch.setenv("MEGASTROY_COOKIE", "foo=bar")
    monkeypatch.setattr(megastroy_parser.settings, "MEGASTROY_HEADLESS", False)

    headers = _build_headers()

    assert headers["Cookie"] == "foo=bar"


def test_build_headers_uses_headless_harvester_when_no_manual_cookie(monkeypatch):
    monkeypatch.delenv("MEGASTROY_COOKIE", raising=False)
    monkeypatch.setattr(megastroy_parser.settings, "MEGASTROY_HEADLESS", True)
    calls = []

    def fake_get_cookie(url, user_agent):
        calls.append((url, user_agent))
        return "__ddg1_=harvested"

    monkeypatch.setattr(megastroy_parser.headless_session, "get_megastroy_cookie", fake_get_cookie)

    headers = _build_headers("https://kazan.megastroy.com/catalog/x")

    assert headers["Cookie"] == "__ddg1_=harvested"
    assert calls == [("https://kazan.megastroy.com/catalog/x", headers["User-Agent"])]


def test_build_headers_manual_cookie_takes_priority_over_headless(monkeypatch):
    # Ручной MEGASTROY_COOKIE не должен запускать headless-харвестер вообще.
    monkeypatch.setenv("MEGASTROY_COOKIE", "manual=cookie")
    monkeypatch.setattr(megastroy_parser.settings, "MEGASTROY_HEADLESS", True)

    def fail_get_cookie(url, user_agent):
        raise AssertionError("headless-харвестер не должен вызываться при ручном cookie")

    monkeypatch.setattr(megastroy_parser.headless_session, "get_megastroy_cookie", fail_get_cookie)

    headers = _build_headers()

    assert headers["Cookie"] == "manual=cookie"


def test_build_headers_headless_disabled_ignores_harvester(monkeypatch):
    monkeypatch.delenv("MEGASTROY_COOKIE", raising=False)
    monkeypatch.setattr(megastroy_parser.settings, "MEGASTROY_HEADLESS", False)

    def fail_get_cookie(url, user_agent):
        raise AssertionError("headless-харвестер не должен вызываться при MEGASTROY_HEADLESS=False")

    monkeypatch.setattr(megastroy_parser.headless_session, "get_megastroy_cookie", fail_get_cookie)

    headers = _build_headers()

    assert "Cookie" not in headers
