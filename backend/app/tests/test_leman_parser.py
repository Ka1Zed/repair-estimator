# app/tests/test_leman_parser.py
# Разбор HTML каталога Лемана без сети/браузера (#276, #277):
# _parse_page разбирает уже готовый HTML одной страницы, fetch_price агрегирует
# страницы, полученные от leman_browser.fetch_pages (мокается ниже — реальный
# patchright-браузер требует РФ-IP и не бежит в CI, см. test_live_parsers.py).
#
# Разметка карточек — из живого дампа каталога lemanapro.ru (SSR React,
# data-qa/data-testid атрибуты стабильны): карточка [data-qa="product"], цена —
# один или два блока [data-testid="price-block-price"/"price-block-unitprice"]
# с атрибутом value и вложенным [data-testid="price-unit"] ("₽/шт.", "₽/кг").
# Леман не гарантирует, в каком именно блоке будет нужная нам единица (у
# шпаклёвки/краски — во вторичном, у плитки/ламината — в основном, у обоев и
# плинтуса вторичного блока может не быть вовсе) — fetch_price берёт первый
# подходящий по единице.

from decimal import Decimal

import pytest

from app.parsers import leman_browser, leman_parser
from app.parsers.leman_parser import (
    CATEGORY_MAP,
    LemanParser,
    _length_m_from_title,
    _parse_page,
)

PAGE_URL = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"


def _price_block(testid: str, value: str, unit: str) -> str:
    return (
        f'<div data-testid="{testid}" value="{value}">'
        f'<span data-testid="price"><span data-testid="price-unit"> ₽/{unit}</span></span>'
        "</div>"
    )


def _item(
    href: str | None,
    name: str = "товар",
    *,
    price: str | None = None,
    price_unit: str = "шт.",
    unitprice: str | None = None,
    unitprice_unit: str = "кг",
) -> str:
    link = f'<a data-qa="product-name" href="{href}">{name}</a>' if href else ""
    blocks = ""
    if price is not None:
        blocks += _price_block("price-block-price", price, price_unit)
    if unitprice is not None:
        blocks += _price_block("price-block-unitprice", unitprice, unitprice_unit)
    return f'<div data-qa="product">{blocks}{link}</div>'


def _page(*items: str) -> str:
    return "<html><body>" + "".join(items) + "</body></html>"


def test_parse_page_returns_price_candidates_and_absolute_url():
    html = _page(
        _item("/product/kraska-a-1/", price="150", price_unit="шт.", unitprice="15", unitprice_unit="л"),
    )
    items = _parse_page(html, PAGE_URL)
    assert len(items) == 1
    candidates, url, name = items[0]
    assert candidates == [(Decimal("150"), "шт."), (Decimal("15"), "л")]
    assert url == "https://kazan.lemanapro.ru/product/kraska-a-1/"
    assert name == "товар"


def test_parse_page_skips_items_without_any_price_block():
    html = _page(_item("/product/free/"), _item("/product/ok-2/", price="100", price_unit="шт."))
    items = _parse_page(html, PAGE_URL)
    assert len(items) == 1
    assert items[0][0] == [(Decimal("100"), "шт.")]


def test_parse_page_normalizes_formatted_price():
    # value может прийти с разделителем тысяч (nbsp/пробел) и запятой-десятичной
    # — не должно молча отсеяться, иначе вся выборка схлопнется в "не найдено цен".
    html = _page(
        _item("/product/a/", price="1\xa0500,50", price_unit="шт."),
        _item("/product/b/", price="2 300", price_unit="шт."),
    )
    items = _parse_page(html, PAGE_URL)
    assert items[0][0] == [(Decimal("1500.50"), "шт.")]
    assert items[1][0] == [(Decimal("2300"), "шт.")]


def test_length_from_title_takes_number_before_standalone_m():
    # "8 см" не должно спутаться с "2.2 м" — "м" внутри "см" не граничит словом.
    assert _length_m_from_title('Плинтус напольный «Белый» 8 см 2.2 м') == Decimal("2.2")


def test_length_from_title_missing_returns_none():
    assert _length_m_from_title("Плинтус без размера в названии") is None


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


def _patch_pages_by_url(monkeypatch, pages_by_url: dict[str, list[str]]):
    # Затирка размазана по нескольким категориям Лемана (#277) — у каждого URL
    # свой набор "страниц".
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)
    monkeypatch.setattr(
        leman_parser.leman_browser,
        "fetch_pages",
        lambda base_url, max_pages: pages_by_url.get(base_url, []),
    )


def test_grout_combines_multiple_category_urls(monkeypatch):
    urls = leman_parser.CATEGORY_MAP["Затирка"]
    assert len(urls) > 1

    def _grout(href, price, unitprice):
        return _item(href, name="Затирка", price=price, price_unit="шт.", unitprice=unitprice, unitprice_unit="кг")

    _patch_pages_by_url(
        monkeypatch,
        {
            urls[0]: [_page(_grout("/product/cementnaya-1/", "532", "80"))],
            urls[1]: [_page(_grout("/product/epoksidnaya-2/", "2850", "150"))],
        },
    )

    parsed = LemanParser().fetch_price("Затирка")

    assert parsed.price_min == Decimal("80")
    assert parsed.price_max == Decimal("150")


def test_grout_continues_when_one_category_fails_to_load(monkeypatch):
    urls = leman_parser.CATEGORY_MAP["Затирка"]

    def _grout(href, unitprice):
        return _item(href, name="Затирка", price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="кг")

    # urls[0] "не отдался" (пустой список страниц), остальные не мокаются
    # (значит fetch_pages вернёт [] по умолчанию из .get(url, [])).
    _patch_pages_by_url(monkeypatch, {urls[1]: [_page(_grout("/product/ok-1/", "100"))]})

    parsed = LemanParser().fetch_price("Затирка")

    assert parsed.price_avg == Decimal("100")


def test_grout_raises_when_all_categories_fail_to_load(monkeypatch):
    _patch_pages_by_url(monkeypatch, {})  # ни один URL не отдал страниц

    with pytest.raises(RuntimeError):
        LemanParser().fetch_price("Затирка")


def test_paint_uses_unitprice_block_not_whole_can_price(monkeypatch):
    # Баг (#277): раньше брали price-block-price (целая банка), а не ₽/л.
    # 2232 ₽/шт. за банку 10 л = 223.2 ₽/л — берём именно второе.
    html = _page(
        _item(
            "/product/kraska-a-1/",
            name="Краска латексная Dufa 10 л",
            price="2232",
            price_unit="шт.",
            unitprice="223.2",
            unitprice_unit="л",
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("223")  # round(223.2)
    assert parsed.price_min == Decimal("223.2")
    # package_size (#306): банка 10 л — ратио цены за упаковку к цене за литр
    # (2232 / 223.2), а не справочные 9 л из materials.json.
    assert parsed.package_size == Decimal("10")


def test_package_size_none_when_only_one_price_block_present(monkeypatch):
    # Карточка без второго блока (например, requests/HTML не отдали unitprice
    # отдельно) — фасовку взять неоткуда, откатываемся на статику выше по стеку.
    html = _page(_item("/product/kraska-b-1/", unitprice="223.2", unitprice_unit="л"))
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.package_size is None


def test_tile_and_laminate_use_primary_block_when_it_is_already_per_m2(monkeypatch):
    # У плитки/ламината основной блок уже "₽/м²", вторичный — "₽/кор." (за
    # упаковку) и не должен использоваться.
    html = _page(
        _item(
            "/product/tile-1/",
            price="1125",
            price_unit="м²",
            unitprice="1368",
            unitprice_unit="кор.",
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Плитка")

    assert parsed.price_avg == Decimal("1125")
    # package_size (#306): у плитки блоки "перевёрнуты" относительно краски —
    # основной уже за м² (база), вторичный "₽/кор." — цена упаковки. Формула
    # та же: package_size = цена_упаковки / цена_базовой_единицы = 1368/1125 м².
    assert parsed.package_size == Decimal("1368") / Decimal("1125")


def test_wallpaper_accepts_pieces_as_rolls(monkeypatch):
    # Обои без вторичного блока — "шт." и есть цена за рулон.
    html = _page(_item("/product/oboi-1/", price="2082", price_unit="шт."))
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Обои")

    assert parsed.price_avg == Decimal("2082")


def test_glue_without_unitprice_block_is_skipped(monkeypatch):
    # Клей иногда приходит вообще без price-block-unitprice — раз ни один
    # блок не даёт "кг", позицию не считаем (не берём цену за мешок как есть).
    html = _page(_item("/product/kley-1/", price="802", price_unit="шт."))
    _patch_pages(monkeypatch, html)

    with pytest.raises(RuntimeError):
        LemanParser().fetch_price("Плиточный клей")


def test_putty_uses_unitprice_kg(monkeypatch):
    html = _page(
        _item(
            "/product/putty-1/",
            name="Шпаклёвка гипсовая универсальная Knauf Фуген 25 кг",
            price="841",
            price_unit="шт.",
            unitprice="33.64",
            unitprice_unit="кг",
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Шпаклевка финишная")

    assert parsed.price_avg == Decimal("34")  # round(33.64)
    assert parsed.price_min == Decimal("33.64")


def test_plintus_normalizes_price_per_piece_by_length_from_title(monkeypatch):
    html = _page(
        _item(
            "/product/plintus-1/",
            name='Плинтус напольный «Белый» 8 см 2.2 м',
            price="220",
            price_unit="шт.",
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("100")  # 220 / 2.2 м
    # package_size (#306) — длина рейки из названия, как и у Мегастроя.
    assert parsed.package_size == Decimal("2.2")


def test_plintus_skips_items_without_parsable_length(monkeypatch):
    html = _page(
        _item("/product/ok-1/", name='Плинтус напольный «Белый» 8 см 2.2 м', price="220", price_unit="шт."),
        _item("/product/no-size-2/", name="Плинтус без размера", price="400", price_unit="шт."),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("100")
    assert "no-size" not in (parsed.source_url or "")


def test_source_url_points_to_product_closest_to_avg(monkeypatch):
    # Цены 100/200/300 (уже ₽/л) → avg=200 → представитель — карточка за 200.
    html = _page(
        _item("/product/kraska-a-1/", price="1000", price_unit="шт.", unitprice="100", unitprice_unit="л"),
        _item("/product/kraska-b-2/", price="2000", price_unit="шт.", unitprice="200", unitprice_unit="л"),
        _item("/product/kraska-c-3/", price="3000", price_unit="шт.", unitprice="300", unitprice_unit="л"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("200")
    assert parsed.source_url == "https://kazan.lemanapro.ru/product/kraska-b-2/"


def test_source_url_falls_back_to_category_when_no_link(monkeypatch):
    # У товара-представителя нет ссылки → деградируем до URL категории, не падаем.
    html = _page(_item(None, price="199", price_unit="шт.", unitprice="199", unitprice_unit="л"))
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.source_url == CATEGORY_MAP["Краска для стен"][0]


def test_fetch_price_dedupes_same_product_across_pages(monkeypatch):
    # Пагинация вернула повтор одной и той же карточки (тот же id в href) на
    # двух "страницах" — не должна задваивать цену в выборке.
    def _paint(href, unitprice):
        return _item(href, price="1000", price_unit="шт.", unitprice=unitprice, unitprice_unit="л")

    page1 = _page(_paint("/product/kraska-a-1/", "150"))
    page2 = _page(_paint("/product/kraska-a-1/", "150"), _paint("/product/kraska-b-2/", "250"))
    _patch_pages(monkeypatch, page1, page2)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_min == Decimal("150")
    assert parsed.price_max == Decimal("250")
    assert parsed.price_avg == Decimal("200")


def test_fetch_price_excludes_outliers_from_spread_and_source(monkeypatch):
    # Выброс 14999 не должен попасть ни в max, ни в товар-представитель (переиспользует
    # filter_outliers — сам хелпер уже покрыт юнит-тестами в test_megastroy_parser.py).
    def _paint(href, unitprice):
        return _item(href, price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="л")

    html = _page(
        _paint("/product/grunt-1/", "175"),
        _paint("/product/kraska-a-2/", "200"),
        _paint("/product/kraska-b-3/", "210"),
        _paint("/product/kraska-c-4/", "220"),
        _paint("/product/kraska-d-5/", "230"),
        _paint("/product/kraska-e-6/", "250"),
        _paint("/product/designer-7/", "14999"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_max == Decimal("250")
    assert parsed.price_max / parsed.price_min < 4
    assert "designer" not in (parsed.source_url or "")


def test_fetch_price_economy_and_premium_return_different_products(monkeypatch):
    """#331: 'Краска для стен эконом'/'премиум' берут нижнюю/верхнюю треть цен той
    же категории (price_band в MATERIAL_UNITS) — разные товары, не только цена."""
    def _paint(href, unitprice):
        return _item(href, price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="л")

    html = _page(
        _paint("/product/paint-a/", "400"),
        _paint("/product/paint-b/", "500"),
        _paint("/product/paint-c/", "600"),
        _paint("/product/paint-d/", "700"),
        _paint("/product/paint-e/", "800"),
        _paint("/product/paint-f/", "900"),
    )
    _patch_pages(monkeypatch, html)

    economy = LemanParser().fetch_price("Краска для стен эконом")
    premium = LemanParser().fetch_price("Краска для стен премиум")
    standard = LemanParser().fetch_price("Краска для стен")

    assert economy.price_max <= Decimal("500")
    assert premium.price_min >= Decimal("800")
    assert economy.source_url != premium.source_url
    assert standard.price_min == Decimal("400")
    assert standard.price_max == Decimal("900")


def test_fetch_price_shares_category_fetch_across_variants(monkeypatch):
    """#341: 'Краска для стен'/'эконом'/'премиум' указывают на тот же base_urls —
    браузер должен дёргаться один раз на весь update_prices, а не по разу на вариант."""
    def _paint(href, unitprice):
        return _item(href, price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="л")

    html = _page(
        _paint("/product/paint-a/", "400"),
        _paint("/product/paint-b/", "500"),
        _paint("/product/paint-c/", "600"),
        _paint("/product/paint-d/", "700"),
        _paint("/product/paint-e/", "800"),
        _paint("/product/paint-f/", "900"),
    )
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)
    calls = []

    def fake_fetch_pages(base_url, max_pages):
        calls.append(base_url)
        return [html]

    monkeypatch.setattr(leman_parser.leman_browser, "fetch_pages", fake_fetch_pages)

    parser = LemanParser()
    parser.fetch_price("Краска для стен")
    parser.fetch_price("Краска для стен эконом")
    parser.fetch_price("Краска для стен премиум")

    # Один браузерный фетч категории на все три материала, не три.
    assert len(calls) == 1


def test_fetch_price_does_not_share_cache_across_different_categories(monkeypatch):
    # Разные категории (краска vs плитка) не должны путать кэш друг с другом.
    paint_html = _page(_item("/product/paint-a/", price="1", price_unit="шт.", unitprice="400", unitprice_unit="л"))
    tile_html = _page(_item("/product/tile-a/", price="500", price_unit="м²"))

    def _pages_by_url(base_url, max_pages):
        if "napolnaya-plitka" in base_url:
            return [tile_html]
        return [paint_html]

    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)
    monkeypatch.setattr(leman_parser.leman_browser, "fetch_pages", _pages_by_url)

    parser = LemanParser()
    paint = parser.fetch_price("Краска для стен")
    tile = parser.fetch_price("Плитка")

    assert paint.price_avg == Decimal("400")
    assert tile.price_avg == Decimal("500")


def test_fetch_price_excludes_irrelevant_subtypes_by_name(monkeypatch):
    # Пробник за 30 ₽ и колеровочная паста — семантический мусор, который роняет
    # min и перекашивает вилку. Отсекаются по имени до статистики: min уже не 30.
    def _paint(href, name, unitprice):
        return _item(href, name=name, price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="л")

    html = _page(
        _paint("/product/probnik-1/", "Пробник краски интерьерной", "30"),
        _paint("/product/koler-2/", "Паста колеровочная белая", "45"),
        _paint("/product/kraska-a-3/", "Краска для стен матовая", "500"),
        _paint("/product/kraska-b-4/", "Краска для стен моющаяся", "600"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_min == Decimal("500")
    assert parsed.price_max == Decimal("600")


def test_fetch_price_excludes_grout_additives_by_name(monkeypatch):
    # Добавки к затиркам и краска для швов — не сама затирка, отсекаются по имени.
    def _grout(href, name, unitprice):
        return _item(href, name=name, price="1", price_unit="шт.", unitprice=unitprice, unitprice_unit="кг")

    html = _page(
        _grout("/product/dobavka-1/", "Добавка для затирки", "300"),
        _grout("/product/paint-2/", "Краска для швов плитки", "400"),
        _grout("/product/zatirka-a-3/", "Затирка цементная CE 40", "80"),
        _grout("/product/zatirka-b-4/", "Затирка эпоксидная", "150"),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Затирка")

    assert parsed.price_min == Decimal("80")
    assert parsed.price_max == Decimal("150")


def test_fetch_price_keeps_sample_when_name_filter_would_empty_it(monkeypatch):
    # Если по именам всё выглядит нерелевантным (разметка сменилась/имена пустые),
    # не схлопываем выборку в ноль — цена не должна уйти в seed из-за фильтра.
    html = _page(
        _item(
            "/product/grunt-1/",
            name="Грунтовка глубокого проникновения",
            price="300",
            price_unit="шт.",
            unitprice="300",
            unitprice_unit="л",
        ),
        _item(
            "/product/grunt-2/",
            name="Грунт-концентрат",
            price="320",
            price_unit="шт.",
            unitprice="320",
            unitprice_unit="л",
        ),
    )
    _patch_pages(monkeypatch, html)

    parsed = LemanParser().fetch_price("Краска для стен")

    assert parsed.price_min == Decimal("300")
    assert parsed.price_max == Decimal("320")


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        LemanParser().fetch_price("Нет такого материала")


def test_page_signature_matches_on_same_products_regardless_of_price():
    # Overflow-детект в fetch_pages сравнивает набор id товаров: та же выдача, что
    # и на прошлой странице (цены/порядок могут отличаться — id нет) → стоп.
    page_a = _page(
        _item("/product/a-1/", price="100", price_unit="шт."),
        _item("/product/b-2/", price="200", price_unit="шт."),
    )
    page_a_reordered = _page(
        _item("/product/b-2/", price="999", price_unit="шт."),
        _item("/product/a-1/", price="100", price_unit="шт."),
    )
    page_b = _page(
        _item("/product/a-1/", price="100", price_unit="шт."),
        _item("/product/c-3/", price="300", price_unit="шт."),
    )

    assert leman_browser._page_signature(page_a) == leman_browser._page_signature(page_a_reordered)
    assert leman_browser._page_signature(page_a) != leman_browser._page_signature(page_b)


def test_page_signature_empty_when_no_products():
    # Пустая/урезанная страница → пустая сигнатура; она не должна ложно
    # срабатывать как «повтор» (в fetch_pages стоп только на непустом совпадении).
    assert leman_browser._page_signature("<html><body></body></html>") == frozenset()


# Переиспользование браузера (#277): без общей сессии на каждую категорию
# (материалов 11+, у затирки ещё 4 подкатегории) заново поднимался бы целый
# процесс Chrome. LemanBrowserSession держит один браузер/контекст и открывает
# по НОВОЙ ВКЛАДКЕ на каждый fetch_pages вместо нового процесса.


class _FakePage:
    def __init__(self, html_pages: list[str]):
        self._html_pages = html_pages
        self.goto_calls: list[str] = []
        self.closed = False
        self.mouse = self

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)

    def wait_for_selector(self, *a, **k):
        pass

    def wait_for_timeout(self, *a, **k):
        pass

    def wheel(self, *a, **k):
        pass

    def content(self):
        idx = len(self.goto_calls) - 1
        if idx >= len(self._html_pages):
            raise RuntimeError("больше страниц нет")
        return self._html_pages[idx]

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, html_pages: list[str]):
        self._html_pages = html_pages
        self.pages_created: list[_FakePage] = []

    def new_page(self):
        page = _FakePage(self._html_pages)
        self.pages_created.append(page)
        return page


def test_fetch_pages_with_context_returns_pages_and_closes_tab():
    context = _FakeContext(["<html>стр1</html>"])

    pages = leman_browser._fetch_pages_with_context(context, "https://kazan.lemanapro.ru/catalogue/x/", 5)

    assert pages == ["<html>стр1</html>"]
    assert len(context.pages_created) == 1
    assert context.pages_created[0].closed is True


def test_fetch_pages_with_context_opens_new_tab_per_call_not_new_browser():
    # Одна и та же сессия (context) используется дважды подряд — как это будет
    # в update_prices на двух разных категориях: должно быть две вкладки, а не
    # два новых процесса браузера (тут проверяем ровно факт вкладки на вызов).
    context = _FakeContext([])

    leman_browser._fetch_pages_with_context(context, "https://kazan.lemanapro.ru/catalogue/a/", 3)
    leman_browser._fetch_pages_with_context(context, "https://kazan.lemanapro.ru/catalogue/b/", 3)

    assert len(context.pages_created) == 2
    assert all(p.closed for p in context.pages_created)


def test_browser_session_fetch_pages_returns_empty_when_context_unavailable():
    # __enter__ не вызывался (patchright не установлен / браузер не поднялся) —
    # _context остаётся None, fetch_pages не должен падать, только вернуть [].
    session = leman_browser.LemanBrowserSession()

    assert session.fetch_pages("https://kazan.lemanapro.ru/catalogue/x/", 5) == []


def test_leman_parser_open_session_is_null_when_live_disabled(monkeypatch):
    # Незачем поднимать Chrome, если LEMAN_LIVE выключен — fetch_price всё равно
    # сразу упадёт в RuntimeError на каждом материале.
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", False)

    with LemanParser().open_session() as session:
        assert session is None


def test_leman_parser_open_session_returns_browser_session_when_live_enabled(monkeypatch):
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)

    session = LemanParser().open_session()

    assert isinstance(session, leman_browser.LemanBrowserSession)


def test_fetch_price_uses_injected_session_instead_of_module_fetch_pages(monkeypatch):
    # update_prices подставляет общую сессию через set_session — fetch_price
    # должен звать её, а не открывать (или закрывать) браузер сам по себе.
    monkeypatch.setattr(leman_parser.settings, "LEMAN_LIVE", True)

    def fail_module_fetch_pages(base_url, max_pages):
        raise AssertionError("не должен звать модульную fetch_pages, когда сессия задана")

    monkeypatch.setattr(leman_parser.leman_browser, "fetch_pages", fail_module_fetch_pages)

    html = _page(
        _item("/product/kraska-a-1/", price="1000", price_unit="шт.", unitprice="200", unitprice_unit="л"),
    )

    class _FakeSession:
        def fetch_pages(self, base_url, max_pages):
            return [html]

    parser = LemanParser()
    parser.set_session(_FakeSession())

    parsed = parser.fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("200")
