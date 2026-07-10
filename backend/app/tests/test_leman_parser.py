# app/tests/test_leman_parser.py
# Разбор HTML каталога Лемана без сети/браузера (#276, plans/2026-07-10-leman-browser-fetch.md):
# _parse_page разбирает уже готовый HTML одной страницы, fetch_price агрегирует
# страницы, полученные от leman_browser.fetch_pages (мокается ниже — реальный
# patchright-браузер требует РФ-IP и не бежит в CI, см. test_live_parsers.py).
#
# Разметка карточек — из живого дампа каталога lemanapro.ru (SSR React,
# data-qa/data-testid атрибуты стабильны): карточка [data-qa="product"] (в этом
# DOM без моб./десктоп дублей — не выдумываем то, что не подтверждено дампом),
# цена — атрибут value на [data-testid="price-block-price"], ссылка —
# a[data-qa="product-name"], id товара — последняя цифровая группа в href.

from decimal import Decimal

import pytest

from app.parsers import leman_parser
from app.parsers.leman_parser import (
    CATEGORY_MAP,
    LemanParser,
    _parse_page,
)

PAGE_URL = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"


def _item(price: str | None, href: str | None) -> str:
    price_block = f'<div data-testid="price-block-price" value="{price}"></div>' if price else ""
    link = f'<a data-qa="product-name" href="{href}">товар</a>' if href else ""
    return f'<div data-qa="product">{price_block}{link}</div>'


def _page(*items: str) -> str:
    return "<html><body>" + "".join(items) + "</body></html>"


def test_parse_page_returns_price_and_absolute_url():
    html = _page(
        _item("150", "/product/kraska-a-1/"),
        _item("250", "https://kazan.lemanapro.ru/product/kraska-b-2/"),
    )
    items = _parse_page(html, PAGE_URL)
    assert items == [
        (Decimal("150"), "https://kazan.lemanapro.ru/product/kraska-a-1/"),
        (Decimal("250"), "https://kazan.lemanapro.ru/product/kraska-b-2/"),
    ]


def test_parse_page_skips_items_without_price():
    html = _page(_item(None, "/product/free/"), _item("100", "/product/ok-2/"))
    items = _parse_page(html, PAGE_URL)
    assert items == [(Decimal("100"), "https://kazan.lemanapro.ru/product/ok-2/")]


def test_parse_page_normalizes_formatted_price():
    # Цена с разделителем тысяч (nbsp/пробел) и запятой-десятичной не должна
    # молча отсеяться — иначе вся выборка схлопнется в "не найдено цен".
    html = _page(
        _item("1\xa0500,50", "/product/a-1/"),
        _item("2 300", "/product/b-2/"),
    )
    items = _parse_page(html, PAGE_URL)
    assert items == [
        (Decimal("1500.50"), "https://kazan.lemanapro.ru/product/a-1/"),
        (Decimal("2300"), "https://kazan.lemanapro.ru/product/b-2/"),
    ]


def _patch_pages(monkeypatch, *pages_html: str):
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)
    monkeypatch.setattr(
        leman_parser.leman_browser, "fetch_pages", lambda base_url, max_pages: list(pages_html)
    )


def test_fetch_price_requires_leman_live(monkeypatch):
    # Без явного включения браузерного фетча Леман вообще не ходит в сеть —
    # сразу уходит в seed-fallback вызывающего кода.
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", False)

    with pytest.raises(RuntimeError):
        LemanParser().fetch_price("Краска для стен")


def test_fetch_price_raises_when_browser_returns_no_pages(monkeypatch):
    _patch_pages(monkeypatch)  # пустой список страниц

    with pytest.raises(RuntimeError):
        LemanParser().fetch_price("Краска для стен")


def test_source_url_points_to_product_closest_to_avg(monkeypatch):
    # Цены 100/200/300 → avg=200 → представитель — карточка за 200.
    html = _page(
        _item("100", "/product/kraska-a-1/"),
        _item("200", "/product/kraska-b-2/"),
        _item("300", "/product/kraska-c-3/"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("200")
    assert parsed.source_url == "https://kazan.lemanapro.ru/product/kraska-b-2/"


def test_source_url_falls_back_to_category_when_no_link(monkeypatch):
    # У товара-представителя нет ссылки → деградируем до URL категории, не падаем.
    html = _page(_item("199", None))
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.source_url == CATEGORY_MAP["Краска для стен"]


def test_fetch_price_dedupes_same_product_across_pages(monkeypatch):
    # Пагинация вернула повтор одной и той же карточки (тот же id в href) на
    # двух "страницах" — не должна задваивать цену в выборке.
    page1 = _page(_item("150", "/product/kraska-a-1/"))
    page2 = _page(_item("150", "/product/kraska-a-1/"), _item("250", "/product/kraska-b-2/"))
    _patch_pages(monkeypatch, page1, page2)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_min == Decimal("150")
    assert parsed.price_max == Decimal("250")
    assert parsed.price_avg == Decimal("200")


def test_fetch_price_excludes_outliers_from_spread_and_source(monkeypatch):
    # Выброс 14999 не должен попасть ни в max, ни в товар-представитель (переиспользует
    # filter_outliers — сам хелпер уже покрыт юнит-тестами в test_megastroy_parser.py).
    html = _page(
        _item("175", "/product/grunt-1/"),
        _item("200", "/product/kraska-a-2/"),
        _item("210", "/product/kraska-b-3/"),
        _item("220", "/product/kraska-c-4/"),
        _item("230", "/product/kraska-d-5/"),
        _item("250", "/product/kraska-e-6/"),
        _item("14999", "/product/designer-7/"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_max == Decimal("250")
    assert parsed.price_max / parsed.price_min < 4
    assert "designer" not in (parsed.source_url or "")


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        LemanParser().fetch_price("Нет такого материала")
