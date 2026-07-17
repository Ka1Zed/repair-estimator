# app/tests/test_megastroy_parser.py
# Разбор HTML каталога Мегастроя без сети (#197, #277): парсер материалов отдаёт
# source_url конкретной карточки товара (та, чья цена ближе к показанной avg), при
# отсутствии ссылки деградирует до URL категории. Мегастрой почти нигде не считает
# цену за базовую единицу сам — у веса/объёма (краска, шпаклёвка, грунтовка, клей,
# затирка) цена всегда "₽/шт" за упаковку целиком, а вес/объём зашит в названии
# ("(10л)", "25 кг") — парсер вычисляет базовую цену сам. Только там, где сайт
# явно считает цену за м²/рулон (плитка, ламинат, обои), берётся текст рядом с
# ценой напрямую. Сетевой смоук — в test_live_parsers.py.

from decimal import Decimal

import pytest

from app.parsers import megastroy_parser
from app.parsers._stats import filter_outliers, price_band_slice
from app.parsers.megastroy_parser import (
    CATEGORY_MAP,
    MegastroyParser,
    _build_headers,
    _cable_length_m_from_title,
    _is_not_startovaya_shpaklevka,
    _is_startovaya_shpaklevka,
    _length_m_from_title,
    _parse_page,
    _pipe_length_m_from_title,
    _quantity_from_title,
    _site_unit,
)

PAINT_URL = CATEGORY_MAP["Краска для стен"].urls[0]


def _item(price: str, href: str | None, title: str = "Краска для стен 1л", unit: str = "шт") -> str:
    # Карточка Мегастроя: первыми идут кнопки-заглушки с href="javascript:"
    # (сравнить/избранное), реальная ссылка на товар — .js-search-product-link.
    # Название по умолчанию несёт "1л" — для материалов с title_unit это делает
    # деление на фасовку no-op'ом, не ломая старые числовые ожидания тестов.
    link = f'<a class="js-search-product-link" href="{href}">{title}</a>' if href else ""
    return (
        '<div class="products-list__item">'
        '<a class="js-compare-product" href="javascript:"></a>'
        '<a class="js-favorite" href="javascript:"></a>'
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


def _collection_item(price_text: str, href: str | None, title: str = "Линолеум А") -> str:
    # Карточка-коллекция (линолеум, #335): нет itemprop=price, цена только
    # текстом "от 325 ₽/м2", ссылка ведёт на /catalog/collection/<id>.
    link = f'<a href="{href}" title="{title}">{title}</a>' if href else ""
    return (
        '<div class="products-list__item">'
        f'<a class="products-list__image-link" href="{href or "#"}"></a>'
        '<div class="products-list__content-title">'
        f"{link}"
        "</div>"
        '<div class="products-price">'
        f'<div class="products-price__value">{price_text}</div>'
        "</div>"
        "</div>"
    )


def _page(*items: str) -> str:
    return "<html><body>" + "".join(items) + "</body></html>"


def test_parse_page_returns_price_url_and_title():
    html = _page(
        _item("150", "/catalog/kraski-dlya-vnutrennih-rabot/kraska-a", title="Краска А 1л"),
        _item("250", "https://kazan.megastroy.com/catalog/x/kraska-b", title="Краска Б 1л"),
    )
    items = _parse_page(html, PAINT_URL)
    assert [(p, u, t) for p, u, _unit, t in items] == [
        (Decimal("150"), "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot/kraska-a", "Краска А 1л"),
        (Decimal("250"), "https://kazan.megastroy.com/catalog/x/kraska-b", "Краска Б 1л"),
    ]


def test_parse_page_skips_items_without_price():
    html = _page(_item("0", "/catalog/x/free"), _item("100", "/catalog/x/ok"))
    items = _parse_page(html, PAINT_URL)
    assert [(p, u) for p, u, _unit, _title in items] == [(Decimal("100"), "https://kazan.megastroy.com/catalog/x/ok")]


def test_site_unit_parses_known_aliases():
    assert _site_unit("179 ₽/шт") == "шт"
    assert _site_unit("399 ₽/м2") == "м²"
    assert _site_unit("1 295 ₽/рул") == "рулон"
    assert _site_unit("нет цены рядом") is None


def test_length_from_title_takes_largest_dimension():
    # Плинтус: "72х2500мм" — сечение 72мм, рейка 2500мм → 2.5 м.
    assert _length_m_from_title("Плинтус напольный ПВХ Lima 72х2500мм Белый") == Decimal("2.5")


def test_length_from_title_handles_triple_dimension():
    assert _length_m_from_title("Ламинат Egger Дуб Гихон светлый 1292х193х7мм 31кл") == Decimal("1.292")


def test_length_from_title_missing_dimension_returns_none():
    assert _length_m_from_title("Товар без размеров в названии") is None


# Фасовка в названии (#277): Мегастрой пишет цену за упаковку ("₽/шт"), вес/объём
# зашит только в названии — "(10л)", "25 кг", "280мл", запятая как разделитель.


def test_quantity_from_title_finds_liters_in_parens():
    assert _quantity_from_title("Грунтовка глубокого проникновения QUALLY (10л)", "л") == Decimal("10")


def test_quantity_from_title_finds_kg_with_space():
    assert _quantity_from_title("Клей для плитки Церезит CM14 Extra 25 кг", "кг") == Decimal("25")


def test_quantity_from_title_does_not_confuse_ml_with_liters():
    # "280мл" не должно засчитаться как литры.
    assert _quantity_from_title("Затирка силиконовая CS 25 Церезит 280мл №04", "л") is None
    assert _quantity_from_title("Затирка силиконовая CS 25 Церезит 280мл №04", "мл") == Decimal("280")


def test_quantity_from_title_ignores_unrelated_numbers():
    # "CM14", "25" (артикул серии) без единицы рядом не должны засчитаться.
    assert _quantity_from_title("Клей Церезит CM14 Extra 25 кг", "кг") == Decimal("25")


def test_quantity_from_title_handles_decimal_comma():
    assert _quantity_from_title("Замазка универсальная 1,4кг ведро", "кг") == Decimal("1.4")


def test_quantity_from_title_missing_unit_returns_none():
    assert _quantity_from_title("Товар без фасовки в названии", "кг") is None


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


# Краска (#277): баг — раньше цена бралась как есть (за банку), теперь делится
# на объём из названия ("(Nл)"), иначе вилка завышалась в разы.


def test_paint_divides_price_by_liters_from_title(monkeypatch):
    html = _page(_item("2232", "/products/1", title="Краска латексная Dufa 10 л"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed.price_avg == Decimal("223")  # round(2232 / 10)
    assert parsed.price_min == Decimal("223.2")


def test_paint_package_size_matches_source_product(monkeypatch):
    # package_size (#306) — фасовка ИМЕННО товара-представителя (10 л из его
    # названия), не справочное значение из materials.json (там для краски — 9).
    html = _page(_item("2232", "/products/1", title="Краска латексная Dufa 10 л"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска для стен")

    assert parsed.package_size == Decimal("10")


def test_paint_without_liters_in_title_is_skipped(monkeypatch):
    html = _page(_item("2232", "/products/1", title="Краска латексная Dufa без объёма"))
    _patch_pages(monkeypatch, html)

    with pytest.raises(RuntimeError):
        MegastroyParser().fetch_price("Краска для стен")


def test_moisture_resistant_paint_divides_price_by_liters_from_title(monkeypatch):
    # Краска влагостойкая (#335): тот же title_unit="л" механизм, что и у обычной
    # краски, категория/фасет отдельные (field142[]=для ванн и кухонь).
    html = _page(_item("2718", "/products/1", title="Краска для кухонь и ванных комнат Olimp 9 л"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Краска влагостойкая")

    assert parsed.price_min == Decimal("302")  # 2718 / 9, единственная цена в выборке


def test_source_url_points_to_product_closest_to_avg(monkeypatch):
    # Цены 100/200/300 (все "1л", деление не меняет числа) → avg=200 → представитель за 200.
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


def test_price_band_slice_takes_low_and_high_terciles():
    items = _items("400", "500", "600", "700", "800", "900")
    low = price_band_slice(items, "low", key=lambda it: it[0])
    high = price_band_slice(items, "high", key=lambda it: it[0])
    assert [p for p, _ in low] == [Decimal("400"), Decimal("500")]
    assert [p for p, _ in high] == [Decimal("800"), Decimal("900")]
    # avg/None — вся выборка без изменений (стандартный tier).
    assert price_band_slice(items, None, key=lambda it: it[0]) == items
    # На маленькой выборке треть выродилась бы в пустоту — не режем.
    small = _items("100", "200")
    assert price_band_slice(small, "low", key=lambda it: it[0]) == small


def test_fetch_price_economy_and_premium_return_different_products(monkeypatch):
    """#331: 'Ламинат эконом'/'Ламинат премиум' берут нижнюю/верхнюю треть цен той
    же категории — разные товары (source_url), а не только разная цена."""
    html = _page(
        _item("400", "/catalog/x/lam-a", title="Ламинат А", unit="м²"),
        _item("500", "/catalog/x/lam-b", title="Ламинат Б", unit="м²"),
        _item("600", "/catalog/x/lam-c", title="Ламинат В", unit="м²"),
        _item("700", "/catalog/x/lam-d", title="Ламинат Г", unit="м²"),
        _item("800", "/catalog/x/lam-e", title="Ламинат Д", unit="м²"),
        _item("900", "/catalog/x/lam-f", title="Ламинат Е", unit="м²"),
    )
    _patch_pages(monkeypatch, html)

    economy = MegastroyParser().fetch_price("Ламинат эконом")
    premium = MegastroyParser().fetch_price("Ламинат премиум")
    standard = MegastroyParser().fetch_price("Ламинат")

    assert economy.price_max <= Decimal("500")
    assert premium.price_min >= Decimal("800")
    assert economy.source_url != premium.source_url
    # Стандарт (без price_band) по-прежнему считает по всей категории.
    assert standard.price_min == Decimal("400")
    assert standard.price_max == Decimal("900")


def test_fetch_price_shares_category_fetch_across_variants(monkeypatch):
    """#341: 'Ламинат'/'эконом'/'премиум' указывают на тот же urls — категория
    должна скачиваться один раз на весь update_prices, а не по разу на вариант."""
    html = _page(
        _item("400", "/catalog/x/lam-a", title="Ламинат А", unit="м²"),
        _item("500", "/catalog/x/lam-b", title="Ламинат Б", unit="м²"),
        _item("600", "/catalog/x/lam-c", title="Ламинат В", unit="м²"),
        _item("700", "/catalog/x/lam-d", title="Ламинат Г", unit="м²"),
        _item("800", "/catalog/x/lam-e", title="Ламинат Д", unit="м²"),
        _item("900", "/catalog/x/lam-f", title="Ламинат Е", unit="м²"),
    )
    calls = []

    class FakeResponse:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(html) if "page=" not in url else FakeResponse("", 404)

    monkeypatch.setattr(megastroy_parser.requests, "get", fake_get)
    monkeypatch.setattr(megastroy_parser.time, "sleep", lambda *a, **k: None)

    parser = MegastroyParser()
    parser.fetch_price("Ламинат")
    parser.fetch_price("Ламинат эконом")
    parser.fetch_price("Ламинат премиум")

    # Один полный фетч категории (стр.1 + стр.2 с 404) на все три материала, не три.
    assert len(calls) == 2


def test_fetch_price_does_not_share_cache_across_different_categories(monkeypatch):
    # Разные категории (краска vs ламинат) не должны путать кэш друг с другом.
    laminate_html = _page(_item("400", "/catalog/x/lam-a", title="Ламинат А", unit="м²"))
    paint_html = _page(_item("223", "/catalog/x/paint-a", title="Краска А 1л"))

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
        if "laminat" in url:
            return FakeResponse(laminate_html)
        return FakeResponse(paint_html)

    monkeypatch.setattr(megastroy_parser.requests, "get", fake_get)
    monkeypatch.setattr(megastroy_parser.time, "sleep", lambda *a, **k: None)

    parser = MegastroyParser()
    laminate = parser.fetch_price("Ламинат")
    paint = parser.fetch_price("Краска для стен")

    assert laminate.price_avg == Decimal("400")
    assert paint.price_avg == Decimal("223")


def test_fetch_price_refetches_category_after_ttl_expires(monkeypatch):
    """#341: кэш живёт не вечно — по истечении TTL повторный вызов идёт в сеть
    заново, а не отдаёт снимок категории многочасовой давности."""
    html = _page(_item("400", "/catalog/x/lam-a", title="Ламинат А", unit="м²"))
    calls = []

    class FakeResponse:
        def __init__(self, text: str, status_code: int = 200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(html) if "page=" not in url else FakeResponse("", 404)

    fake_now = [1000.0]
    monkeypatch.setattr(megastroy_parser.requests, "get", fake_get)
    monkeypatch.setattr(megastroy_parser.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(megastroy_parser.time, "monotonic", lambda: fake_now[0])

    parser = MegastroyParser()
    parser.fetch_price("Ламинат")
    assert len(calls) == 2  # стр.1 + стр.2 с 404

    fake_now[0] += megastroy_parser._CATEGORY_CACHE_TTL_SECONDS + 1
    parser.fetch_price("Ламинат эконом")
    assert len(calls) == 4  # TTL истёк — категория скачана заново


def test_unknown_material_raises():
    with pytest.raises(ValueError):
        MegastroyParser().fetch_price("Нет такого материала")


# Шпаклёвка/клей/затирка/грунтовка (#277): та же логика деления на фасовку из
# названия, что и у краски, просто с единицей "кг"/"л".


def test_putty_divides_price_by_kg_from_title(monkeypatch):
    html = _page(_item("841", "/products/putty", title="Шпаклёвка Knauf Фуген 25 кг"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка финишная")

    assert parsed.price_avg == Decimal("34")  # round(841/25)


# Классификация шпаклёвки по названию (#386): у Мегастроя нет facet, чисто
# отделяющего стартовую от финишной/универсальной — решаем по маркерам в
# названии карточки, аналогично _is_relevant в leman_parser.py.


def test_is_startovaya_shpaklevka_matches_start_markers():
    assert _is_startovaya_shpaklevka("Шпаклевка стартовая гипсовая ЕК К200 20 кг")
    assert _is_startovaya_shpaklevka("Шпатлевка базовая выравнивающая Волма 30 кг")
    assert _is_startovaya_shpaklevka("Шпаклевка для стен под штукатурку 25 кг")


def test_is_startovaya_shpaklevka_rejects_finish_and_universal():
    assert not _is_startovaya_shpaklevka("Шпаклевка финишная полимерная Ветонит 20 кг")
    assert not _is_startovaya_shpaklevka("Шпаклевка универсальная (старт+финиш) 20 кг")
    assert not _is_startovaya_shpaklevka("Шпаклёвка Knauf Фуген 25 кг")  # нет маркеров вовсе


def test_is_not_startovaya_shpaklevka_excludes_start_markers():
    assert not _is_not_startovaya_shpaklevka("Шпаклевка стартовая гипсовая 20 кг")
    assert _is_not_startovaya_shpaklevka("Шпаклевка финишная полимерная Ветонит 20 кг")
    assert _is_not_startovaya_shpaklevka("Шпаклёвка Knauf Фуген 25 кг")


def test_startovaya_shpaklevka_filters_finish_products_from_shared_category(monkeypatch):
    # #386: обе категории теперь могут читать общую страницу shpaklevka без
    # узкого facet'а — классификация по названию должна развести карточки
    # правильно, не полагаясь на URL.
    html = _page(
        _item("810", "/products/start", title="Шпаклевка стартовая гипсовая ЕК К200 20 кг"),
        _item("498", "/products/finish", title="Шпаклевка финишная полимерная ЕК К300 20 кг"),
        _item("495", "/products/universal", title="Шпаклевка универсальная Волма 20 кг"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка стартовая")

    assert "start" in (parsed.source_url or "")
    assert "finish" not in (parsed.source_url or "")
    assert "universal" not in (parsed.source_url or "")


def test_startovaya_shpaklevka_falls_back_to_full_category_when_no_markers_match(monkeypatch):
    # Разметка/названия не дали ни одного совпадения по маркерам — фильтр не
    # должен обнулить выдачу целиком (иначе цена уходит в seed без нужды).
    html = _page(_item("750", "/products/putty", title="Шпаклёвка Knauf Фуген 25 кг"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка стартовая")

    assert parsed.price_avg == Decimal("30")  # round(750/25)


def test_finishing_shpaklevka_excludes_startovaya_leakage(monkeypatch):
    # Подстраховка (#386): даже если под узкий facet попала явно стартовая
    # карточка, она не должна засорять выдачу «Шпаклевка финишная».
    html = _page(
        _item("498", "/products/finish", title="Шпаклевка финишная полимерная ЕК К300 20 кг"),
        _item("400", "/products/start-leak", title="Шпаклевка стартовая гипсовая 20 кг"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка финишная")

    assert "start-leak" not in (parsed.source_url or "")


def test_glue_divides_price_by_kg_from_title(monkeypatch):
    html = _page(_item("905", "/products/glue", title="Клей для плитки Церезит CM14 Extra 25 кг"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плиточный клей")

    assert parsed.price_avg == Decimal("36")  # round(905/25)


def test_primer_divides_price_by_liters_from_title(monkeypatch):
    html = _page(_item("699", "/products/grunt", title="Грунтовка глубокого проникновения QUALLY (10л)"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Грунтовка")

    assert parsed.price_avg == Decimal("70")  # round(699/10)


def test_grout_excludes_items_priced_in_milliliters(monkeypatch):
    # Силиконовая затирка в мл (герметик-тюбик) — другая форма товара, не считаем.
    html = _page(
        _item("2850", "/products/epoxy", title="Затирка эпоксидная STARLIKE (1кг)"),
        _item("1045", "/products/silicone", title="Затирка силиконовая CS 25 280мл №04"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Затирка")

    assert parsed.price_avg == Decimal("2850")
    assert "silicone" not in (parsed.source_url or "")


def test_material_without_matching_quantity_raises(monkeypatch):
    # Ни одна позиция не дала распознаваемую фасовку → RuntimeError → seed.
    html = _page(_item("179", "/products/x", title="Товар без фасовки в названии"))
    _patch_pages(monkeypatch, html)

    with pytest.raises(RuntimeError):
        MegastroyParser().fetch_price("Шпаклевка стартовая")


# Нетиповая (мелкая) фасовка кг-материалов (#382): категория обычно содержит больше
# карточек мелкой фасовки, чем мешков — без фильтра price_avg и представитель
# съезжают к цене мелкой упаковки.


def test_putty_filters_out_undersized_package_when_reference_given(monkeypatch):
    html = _page(
        _item("156", "/products/putty-small", title="Шпаклёвка Knauf Фуген 5 кг"),  # 31.2 ₽/кг
        _item("750", "/products/putty-bag", title="Шпаклёвка Knauf Фуген 25 кг"),  # 30 ₽/кг
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price(
        "Шпаклевка финишная", reference_package_size=Decimal("25")
    )

    assert parsed.price_avg == Decimal("30")
    assert parsed.package_size == Decimal("25")
    assert "putty-bag" in (parsed.source_url or "")


def test_putty_without_reference_package_size_keeps_all_items(monkeypatch):
    # reference_package_size=None (дефолт, как у всех старых вызовов) — фильтр не
    # применяется, поведение как раньше.
    html = _page(
        _item("156", "/products/putty-small", title="Шпаклёвка Knauf Фуген 5 кг"),
        _item("750", "/products/putty-bag", title="Шпаклёвка Knauf Фуген 25 кг"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Шпаклевка финишная")

    assert parsed.price_min == Decimal("30")
    assert parsed.price_max == Decimal("31.2")


def test_putty_all_undersized_raises_when_reference_given(monkeypatch):
    html = _page(_item("156", "/products/putty-small", title="Шпаклёвка Knauf Фуген 5 кг"))
    _patch_pages(monkeypatch, html)

    with pytest.raises(RuntimeError):
        MegastroyParser().fetch_price("Шпаклевка финишная", reference_package_size=Decimal("25"))


# Плинтус (#277): витринная единица — "шт" (рейка фиксированной длины), наша
# база — метр; цену приводим делением на длину рейки из названия.


def test_plintus_normalizes_price_per_piece_to_price_per_meter(monkeypatch):
    html = _page(_item("560", "/products/plintus-a", title="Плинтус напольный ПВХ Lima 72х2500мм Белый"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("224")  # 560 / 2.5 м


def test_plintus_package_size_equals_rail_length(monkeypatch):
    # package_size (#306) — длина рейки товара-представителя, а не справочная
    # константа (в materials.json у плинтуса package_size=1).
    html = _page(_item("560", "/products/plintus-a", title="Плинтус напольный ПВХ Lima 72х2500мм Белый"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плинтус")

    assert parsed.package_size == Decimal("2.5")


def test_plintus_skips_items_without_parsable_length(monkeypatch):
    html = _page(
        _item("560", "/products/ok", title="Плинтус напольный ПВХ Lima 72х2500мм Белый"),
        _item("400", "/products/no-size", title="Плинтус без размера в названии"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Плинтус")

    assert parsed.price_avg == Decimal("224")
    assert "no-size" not in (parsed.source_url or "")


def test_cable_length_from_title_reads_parenthesized_meters():
    assert _cable_length_m_from_title("Кабель ВВГнг 3х1,5 (10м) ГОСТ") == Decimal("10")
    assert _cable_length_m_from_title("Кабель ВВГнг(A)-LS 3х2,5 (20м) ГОСТ") == Decimal("20")


def test_cable_length_from_title_ignores_unit_marker_without_digit():
    # "Кабель АВВГ 3-2.5(м)" — "(м)" тут маркер единицы "на отрез", не длина.
    assert _cable_length_m_from_title("Кабель АВВГ 3-2.5(м)") is None


def test_cable_length_from_title_missing_length_returns_none():
    assert _cable_length_m_from_title("Кабель медный ВВГнг-LS 2х2,5 ГОСТ") is None


# Кабель (#335): единственная категория, где ОДНА карточка может быть уже
# "₽/м" ("на отрез"), а другая — "₽/шт" за бухту целиком с длиной в названии
# ("...(10м)...") — решаем по каждой карточке отдельно, не по категории целиком.


def test_cable_takes_price_as_is_when_already_priced_per_meter(monkeypatch):
    html = _page(_item("305", "/products/cable-otrez", title="Кабель ВВГнг 3х6 ГОСТ", unit="м"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Кабель электрический")

    assert parsed.price_avg == Decimal("305")
    assert parsed.package_size is None


def test_cable_normalizes_coil_price_by_length_in_title(monkeypatch):
    html = _page(_item("895", "/products/cable-coil", title="Кабель ВВГнг 3х1,5 (10м) ГОСТ"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Кабель электрический")

    # price_avg — round(statistics.mean(...)), сверяем нечувствительный к
    # округлению price_min вместо него (единственная цена в выборке).
    assert parsed.price_min == Decimal("89.5")
    # package_size (#306) — длина бухты, как и у плинтуса.
    assert parsed.package_size == Decimal("10")


def test_cable_skips_items_without_meter_unit_or_parsable_coil_length(monkeypatch):
    html = _page(
        _item("305", "/products/ok-otrez", title="Кабель ВВГнг 3х6 ГОСТ", unit="м"),
        _item("895", "/products/ok-coil", title="Кабель ВВГнг 3х1,5 (10м) ГОСТ"),
        _item("500", "/products/no-length", title="Кабель без длины в названии"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Кабель электрический")

    assert "no-length" not in (parsed.source_url or "")
    assert parsed.price_min == Decimal("89.5")
    assert parsed.price_max == Decimal("305")


def test_pipe_length_from_title_reads_length_after_word():
    assert _pipe_length_m_from_title(
        "Труба полипропиленовая армированная стекловолокном PN20 d20х2,8мм, длина трубы 2м"
    ) == Decimal("2")
    assert _pipe_length_m_from_title("Труба ПНД для водоснабжения PN10 d32мм, длина 4м") == Decimal("4")


def test_pipe_length_from_title_missing_length_returns_none():
    assert _pipe_length_m_from_title("Кран полипропиленовый шаровый PN25 d20мм") is None


# Труба (#335): всегда "₽/шт" за штуку фиксированной длины — длина только в
# названии ("длина трубы 2м"), в отличие от кабеля тут нет случая "уже ₽/м".


def test_pipe_normalizes_price_per_piece_by_length_in_title(monkeypatch):
    html = _page(
        _item(
            "115",
            "/products/pipe-a",
            title="Труба полипропиленовая для горячего и холодного водоснабжения PN20 d20х3,4мм, длина трубы 2м",
        )
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Труба водопроводная")

    assert parsed.price_min == Decimal("57.5")  # 115 / 2 м
    assert parsed.package_size == Decimal("2")


def test_pipe_skips_items_without_parsable_length(monkeypatch):
    html = _page(
        _item("115", "/products/ok", title="Труба полипропиленовая PN20 d20х3,4мм, длина трубы 2м"),
        _item("9", "/products/fitting", title="Угольник полипропиленовый соединительный под пайку 90°"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Труба водопроводная")

    assert "fitting" not in (parsed.source_url or "")
    assert parsed.price_min == Decimal("57.5")


# Плитка/ламинат/обои (#277): сайт сам считает цену за м²/рулон и пишет её текстом
# рядом с ценой — тут фильтруем по этому тексту напрямую, без вычислений.


def test_tile_and_laminate_use_site_computed_unit(monkeypatch):
    html = _page(_item("399", "/products/laminate", title="Ламинат Дуб", unit="м2"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Ламинат")

    assert parsed.price_avg == Decimal("399")
    # package_size (#306): страница категории не показывает отдельную "цену за
    # коробку" для site_unit-материалов — фасовку взять неоткуда, откатываемся
    # на статичный Material.package_size выше по стеку (estimates.py).
    assert parsed.package_size is None


def test_wallpaper_uses_site_computed_unit(monkeypatch):
    html = _page(_item("1295", "/products/oboi", title="Обои декоративные", unit="рул"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Обои")

    assert parsed.price_avg == Decimal("1295")


def test_socket_takes_price_as_is_without_unit_normalization(monkeypatch):
    # #335: розетка — первый материал без site_unit/title_unit/normalize_length_mm,
    # сайт и так пишет "₽/шт" — цена берётся как есть, единица не проверяется.
    html = _page(_item("399", "/products/rozetka", title="Розетка SE Art Gallery карбон"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Розетка")

    assert parsed.price_avg == Decimal("399")


def test_socket_economy_takes_lower_tercile(monkeypatch):
    html = _page(
        _item("150", "/products/rozetka-a", title="Розетка А"),
        _item("250", "/products/rozetka-b", title="Розетка Б"),
        _item("350", "/products/rozetka-c", title="Розетка В"),
        _item("450", "/products/rozetka-d", title="Розетка Г"),
        _item("550", "/products/rozetka-e", title="Розетка Д"),
        _item("650", "/products/rozetka-f", title="Розетка Е"),
    )
    _patch_pages(monkeypatch, html)

    economy = MegastroyParser().fetch_price("Розетка эконом")
    standard = MegastroyParser().fetch_price("Розетка")

    assert economy.price_max <= Decimal("250")
    assert standard.price_min == Decimal("150")
    assert standard.price_max == Decimal("650")


def test_parse_page_reads_collection_card_price_from_text():
    # #335: линолеум показывает карточки-коллекции без itemprop=price.
    html = _page(_collection_item("от 325 ₽/м2", "/catalog/collection/13673", title="Линолеум BAZIS"))
    items = _parse_page(html, "https://kazan.megastroy.com/catalog/linoleum")
    assert [(p, u, unit, t) for p, u, unit, t in items] == [
        (
            Decimal("325"),
            "https://kazan.megastroy.com/catalog/collection/13673",
            "м²",
            "Линолеум BAZIS",
        )
    ]


def test_linoleum_reads_price_from_collection_cards(monkeypatch):
    html = _page(
        _collection_item("от 325 ₽/м2", "/catalog/collection/1", title="Линолеум А"),
        _collection_item("от 450 ₽/м2", "/catalog/collection/2", title="Линолеум Б"),
    )
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Линолеум")

    assert parsed.price_min == Decimal("325")
    assert parsed.price_max == Decimal("450")
    # site_unit-материалы не дают отдельной "цены за упаковку" (#306) — как у
    # плитки/ламината/обоев.
    assert parsed.package_size is None


def test_light_takes_price_as_is_without_unit_normalization(monkeypatch):
    # #335: точечный светильник — как розетка, цена "₽/шт" берётся как есть.
    html = _page(_item("450", "/products/svetilnik", title="Точечный светильник LED"))
    _patch_pages(monkeypatch, html)

    parsed = MegastroyParser().fetch_price("Светильник")

    assert parsed.price_avg == Decimal("450")


def test_tile_combines_two_categories(monkeypatch):
    granit_html = _page(_item("1000", "/products/granit", title="Керамогранит А", unit="м2"))
    keramika_html = _page(_item("1200", "/products/keramika", title="Плитка керамическая Б", unit="м2"))

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
