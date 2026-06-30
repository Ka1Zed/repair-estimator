# app/tests/test_megastroy_parser.py
# Разбор HTML каталога Мегастроя без сети (#197): парсер материалов отдаёт source_url
# конкретной карточки товара (та, чья цена ближе к показанной avg), а при отсутствии
# ссылки деградирует до URL категории. Сетевой смоук — в test_live_parsers.py.

from decimal import Decimal

import pytest

from app.parsers import megastroy_parser
from app.parsers.megastroy_parser import CATEGORY_MAP, MegastroyParser, _parse_page

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


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        MegastroyParser().fetch_price("Нет такого материала")
