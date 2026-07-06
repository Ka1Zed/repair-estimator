# app/tests/test_megastroy_parser.py
# Разбор HTML каталога Мегастроя без сети (#197): парсер материалов отдаёт source_url
# конкретной карточки товара (та, чья цена ближе к показанной avg), а при отсутствии
# ссылки деградирует до URL категории. Сетевой смоук — в test_live_parsers.py.

from decimal import Decimal

import pytest

from app.parsers import megastroy_parser
from app.parsers._stats import filter_outliers
from app.parsers.megastroy_parser import (
    CATEGORY_MAP,
    MegastroyParser,
    _build_headers,
    _parse_page,
)

PAGE_URL = "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot"


def _item(price: str, href: str | None) -> str:
    # Карточка Мегастроя: первыми идут кнопки-заглушки с href="javascript:"
    # (сравнить/избранное), реальная ссылка на товар — .js-search-product-link.
    link = f'<a class="js-search-product-link" href="{href}">товар</a>' if href else ""
    return (
        '<div class="products-list__item">'
        '<a class="js-compare-product" href="javascript:"></a>'
        '<a class="js-favorite" href="javascript:"></a>'
        f"{link}"
        f'<meta itemprop="price" content="{price}">'
        "</div>"
    )


def _page(*items: str) -> str:
    return "<html><body>" + "".join(items) + "</body></html>"


def test_parse_page_returns_price_and_absolute_url():
    html = _page(
        _item("150", "/catalog/kraski-dlya-vnutrennih-rabot/kraska-a"),
        _item("250", "https://kazan.megastroy.com/catalog/x/kraska-b"),
    )
    items = _parse_page(html, PAGE_URL)
    assert items == [
        (Decimal("150"), "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot/kraska-a"),
        (Decimal("250"), "https://kazan.megastroy.com/catalog/x/kraska-b"),
    ]


def test_parse_page_skips_items_without_price():
    html = _page(_item("0", "/catalog/x/free"), _item("100", "/catalog/x/ok"))
    items = _parse_page(html, PAGE_URL)
    assert items == [(Decimal("100"), "https://kazan.megastroy.com/catalog/x/ok")]


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

    assert parsed.source_url == CATEGORY_MAP["Краска для стен"]


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


# _build_headers: приоритет MEGASTROY_COOKIE (ручной hand-off) над
# MEGASTROY_HEADLESS (beta-харвестер), см. plans/2026-06-30-beta-headless-parser.md.


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
