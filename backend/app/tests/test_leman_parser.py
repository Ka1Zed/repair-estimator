# app/tests/test_leman_parser.py
# Разбор HTML каталога Лемана без сети (#276): парсер материалов отдаёт source_url
# конкретной карточки товара (та, чья цена ближе к показанной avg), а при отсутствии
# ссылки деградирует до URL категории. Сетевой смоук — в test_live_parsers.py.
#
# Разметка карточек — из реального HTML lemanapro.ru (SSR React, data-qa/data-testid
# атрибуты стабильны), не выдумана: контейнер [data-qa="products-list"], карточка
# отмечена data-sl-product-id (рендерится дважды — моб./десктоп копия с одинаковыми
# данными), цена — атрибут value на [data-testid="price-block-price"], ссылка —
# a[data-qa="product-name"].

from decimal import Decimal

import pytest

from app.parsers import leman_parser
from app.parsers.leman_parser import (
    CATEGORY_MAP,
    LemanParser,
    _build_headers,
    _parse_page,
)

PAGE_URL = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"


def _item(product_id: str, price: str | None, href: str | None) -> str:
    price_block = f'<div data-testid="price-block-price" value="{price}"></div>' if price else ""
    link = f'<a data-qa="product-name" href="{href}">товар</a>' if href else ""
    return (
        f'<div data-sl-product-id="{product_id}">'
        f"{price_block}"
        f"{link}"
        "</div>"
    )


def _duplicate(item_html: str) -> str:
    # Мобильная/десктопная копия одной и той же карточки в SSR-разметке.
    return item_html + item_html


def _page(*items: str) -> str:
    return '<html><body><div data-qa="products-list">' + "".join(items) + "</div></body></html>"


def test_parse_page_returns_price_and_absolute_url():
    html = _page(
        _item("1", "150", "/product/kraska-a-1/"),
        _item("2", "250", "https://kazan.lemanapro.ru/product/kraska-b-2/"),
    )
    items = _parse_page(html, PAGE_URL)
    assert items == [
        (Decimal("150"), "https://kazan.lemanapro.ru/product/kraska-a-1/"),
        (Decimal("250"), "https://kazan.lemanapro.ru/product/kraska-b-2/"),
    ]


def test_parse_page_dedupes_mobile_desktop_copies():
    # Одна и та же карточка (тот же data-sl-product-id) рендерится дважды —
    # не должна задваивать цену в выборке.
    html = _page(_duplicate(_item("1", "150", "/product/kraska-a-1/")))
    items = _parse_page(html, PAGE_URL)
    assert items == [(Decimal("150"), "https://kazan.lemanapro.ru/product/kraska-a-1/")]


def test_parse_page_skips_items_without_price():
    html = _page(_item("1", None, "/product/free/"), _item("2", "100", "/product/ok/"))
    items = _parse_page(html, PAGE_URL)
    assert items == [(Decimal("100"), "https://kazan.lemanapro.ru/product/ok/")]


def test_parse_page_normalizes_formatted_price():
    # Цена с разделителем тысяч (nbsp/пробел) и запятой-десятичной не должна
    # молча отсеяться — иначе вся выборка схлопнется в "не найдено цен".
    html = _page(
        _item("1", "1\xa0500,50", "/product/a/"),
        _item("2", "2 300", "/product/b/"),
    )
    items = _parse_page(html, PAGE_URL)
    assert items == [
        (Decimal("1500.50"), "https://kazan.lemanapro.ru/product/a/"),
        (Decimal("2300"), "https://kazan.lemanapro.ru/product/b/"),
    ]


def _patch_pages(monkeypatch, page_html: str):
    '''Первая страница каталога отдаёт page_html, со 2-й — пустая (конец пагинации).'''

    class FakeResponse:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_get(url, **kwargs):
        return FakeResponse(page_html) if "page=" not in url else FakeResponse("<html></html>")

    monkeypatch.setattr(leman_parser.requests, "get", fake_get)
    monkeypatch.setattr(leman_parser.time, "sleep", lambda *a, **k: None)


def test_source_url_points_to_product_closest_to_avg(monkeypatch):
    # Цены 100/200/300 → avg=200 → представитель — карточка за 200.
    html = _page(
        _item("1", "100", "/product/kraska-a/"),
        _item("2", "200", "/product/kraska-b/"),
        _item("3", "300", "/product/kraska-c/"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("200")
    assert parsed.source_url == "https://kazan.lemanapro.ru/product/kraska-b/"


def test_source_url_falls_back_to_category_when_no_link(monkeypatch):
    # У товара-представителя нет ссылки → деградируем до URL категории, не падаем.
    html = _page(_item("1", "199", None))
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.source_url == CATEGORY_MAP["Краска для стен"]


def test_fetch_price_excludes_outliers_from_spread_and_source(monkeypatch):
    # Выброс 14999 не должен попасть ни в max, ни в товар-представитель (переиспользует
    # filter_outliers — сам хелпер уже покрыт юнит-тестами в test_megastroy_parser.py).
    html = _page(
        _item("1", "175", "/product/grunt/"),
        _item("2", "200", "/product/kraska-a/"),
        _item("3", "210", "/product/kraska-b/"),
        _item("4", "220", "/product/kraska-c/"),
        _item("5", "230", "/product/kraska-d/"),
        _item("6", "250", "/product/kraska-e/"),
        _item("7", "14999", "/product/designer/"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_max == Decimal("250")
    assert parsed.price_max / parsed.price_min < 4
    assert "designer" not in (parsed.source_url or "")


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        LemanParser().fetch_price("Нет такого материала")


# _build_headers: приоритет LEMAN_COOKIE (ручной hand-off) над LEMAN_HEADLESS
# (beta-харвестер) — тот же паттерн, что у Мегастроя.


def test_build_headers_no_cookie_by_default(monkeypatch):
    monkeypatch.delenv("LEMAN_COOKIE", raising=False)
    monkeypatch.setattr(leman_parser.settings, "LEMAN_HEADLESS", False)

    headers = _build_headers()

    assert "Cookie" not in headers


def test_build_headers_uses_manual_cookie(monkeypatch):
    monkeypatch.setenv("LEMAN_COOKIE", "foo=bar")
    monkeypatch.setattr(leman_parser.settings, "LEMAN_HEADLESS", False)

    headers = _build_headers()

    assert headers["Cookie"] == "foo=bar"


def test_build_headers_uses_headless_harvester_when_no_manual_cookie(monkeypatch):
    monkeypatch.delenv("LEMAN_COOKIE", raising=False)
    monkeypatch.setattr(leman_parser.settings, "LEMAN_HEADLESS", True)
    calls = []

    def fake_get_cookie(url, user_agent):
        calls.append((url, user_agent))
        return "sess=harvested"

    monkeypatch.setattr(leman_parser.headless_session, "get_leman_cookie", fake_get_cookie)

    headers = _build_headers("https://kazan.lemanapro.ru/catalogue/x/")

    assert headers["Cookie"] == "sess=harvested"
    assert calls == [("https://kazan.lemanapro.ru/catalogue/x/", headers["User-Agent"])]


def test_build_headers_manual_cookie_takes_priority_over_headless(monkeypatch):
    # Ручной LEMAN_COOKIE не должен запускать headless-харвестер вообще.
    monkeypatch.setenv("LEMAN_COOKIE", "manual=cookie")
    monkeypatch.setattr(leman_parser.settings, "LEMAN_HEADLESS", True)

    def fail_get_cookie(url, user_agent):
        raise AssertionError("headless-харвестер не должен вызываться при ручном cookie")

    monkeypatch.setattr(leman_parser.headless_session, "get_leman_cookie", fail_get_cookie)

    headers = _build_headers()

    assert headers["Cookie"] == "manual=cookie"


def test_build_headers_headless_disabled_ignores_harvester(monkeypatch):
    monkeypatch.delenv("LEMAN_COOKIE", raising=False)
    monkeypatch.setattr(leman_parser.settings, "LEMAN_HEADLESS", False)

    def fail_get_cookie(url, user_agent):
        raise AssertionError("headless-харвестер не должен вызываться при LEMAN_HEADLESS=False")

    monkeypatch.setattr(leman_parser.headless_session, "get_leman_cookie", fail_get_cookie)

    headers = _build_headers()

    assert "Cookie" not in headers
