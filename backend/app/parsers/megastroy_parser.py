import logging
import os
import re
import statistics
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import headless_session
from app.parsers._stats import filter_outliers, price_band_slice
from app.parsers.base import BaseParser, ParsedPrice, DEFAULT_HEADERS, DEFAULT_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaterialCategory:
    # Одна или несколько категорий Мегастроя, откуда берём цены материала
    # (плитка размазана по "керамогранит" и "керамическая плитка", #277).
    urls: tuple[str, ...]
    # Единица, которую сайт САМ показывает текстом рядом с ценой ("399 ₽/м2",
    # "1295 ₽/рул") и которая уже верна без вычислений — это касается только
    # категорий, где Мегастрой явно считает цену за м²/рулон (плитка, ламинат,
    # обои). Для остальных материалов (краска, шпаклёвка, грунтовка, клей,
    # затирка) сайт вне зависимости от фасовки всегда пишет "₽/шт" — там
    # нормализуем сами по названию (см. title_unit).
    site_unit: str | None = None
    # Единица фасовки, которую ищем в НАЗВАНИИ товара ("(10л)", "25 кг"), чтобы
    # посчитать цену за базовую единицу делением на неё самим.
    title_unit: str | None = None
    # Плинтус — особый разбор: размерный блок "72х2500мм" в названии, а не
    # "число+кг/л" — длина рейки берётся отдельной функцией (_length_m_from_title).
    normalize_length_mm: bool = False
    # Вариант по уровню комплектации (#331): "low"/"high" — нижняя/верхняя
    # треть цен категории (см. price_band_slice), None — вся категория как
    # раньше (стандарт/avg). Сайт не даёт facet «бренд/класс» вне краски —
    # это приближение, а не курированный список брендов (docs/price-sources.md).
    price_band: str | None = None


_SHPAKLEVKA = "https://kazan.megastroy.com/catalog/shpaklevka"

# Карта: материал в БД -> категория(и) Мегастроя (Казань) с фильтром, где нужен.
CATEGORY_MAP: dict[str, MaterialCategory] = {
    "Краска для стен": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",),
        title_unit="л",
    ),
    # Варианты по уровню (#331) — та же категория, нижняя/верхняя треть цен
    # (price_band, см. docs/price-sources.md).
    "Краска для стен эконом": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",),
        title_unit="л", price_band="low",
    ),
    "Краска для стен премиум": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",),
        title_unit="л", price_band="high",
    ),
    "Краска потолочная": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot?field142[]=для потолков",
        ),
        title_unit="л",
    ),
    "Краска потолочная премиум": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot?field142[]=для потолков",
        ),
        title_unit="л", price_band="high",
    ),
    "Шпаклевка стартовая": MaterialCategory(
        urls=(f"{_SHPAKLEVKA}?field206[]=для заделки щелей, выбоин, трещин",),
        title_unit="кг",
    ),
    "Шпаклевка финишная": MaterialCategory(
        urls=(f"{_SHPAKLEVKA}?field206[]=под окраску и оклейку обоями",),
        title_unit="кг",
    ),
    "Грунтовка": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/grunty",),
        title_unit="л",
    ),
    "Плиточный клей": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/kley-dlya-plitki-2",),
        title_unit="кг",
    ),
    "Затирка": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/zatirki-dlya-plitki",),
        title_unit="кг",
    ),
    "Плитка": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/keramogranit",
            "https://kazan.megastroy.com/catalog/keramicheskaya-plitka",
        ),
        site_unit="м²",
    ),
    "Плитка эконом": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/keramogranit",
            "https://kazan.megastroy.com/catalog/keramicheskaya-plitka",
        ),
        site_unit="м²", price_band="low",
    ),
    "Плитка премиум": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/keramogranit",
            "https://kazan.megastroy.com/catalog/keramicheskaya-plitka",
        ),
        site_unit="м²", price_band="high",
    ),
    "Ламинат": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/laminat",),
        site_unit="м²",
    ),
    "Ламинат эконом": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/laminat",),
        site_unit="м²", price_band="low",
    ),
    "Ламинат премиум": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/laminat",),
        site_unit="м²", price_band="high",
    ),
    "Обои": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/dekorativnye-oboi",),
        site_unit="рулон",
    ),
    "Обои эконом": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/dekorativnye-oboi",),
        site_unit="рулон", price_band="low",
    ),
    "Обои премиум": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/dekorativnye-oboi",),
        site_unit="рулон", price_band="high",
    ),
    "Плинтус": MaterialCategory(
        urls=("https://kazan.megastroy.com/catalog/plintusy",),
        normalize_length_mm=True,
    ),
}

# Расширяет DEFAULT_HEADERS собственным Accept — не чистый дубль (#278).
HEADERS = {**DEFAULT_HEADERS, "Accept": "text/html,application/xhtml+xml"}

REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT      # таймаут запроса, сек
REQUEST_DELAY = 1.0       # пауза между страницами, чтобы не долбить сайт
MAX_PAGES = 20            # защита от бесконечного цикла

# Вариантные материалы (эконом/премиум, #331) указывают на тот же urls, что и
# стандарт — кэш сырых цен категории по urls (#341), чтобы update_prices не
# качал одну и ту же выдачу 2-3 раза подряд для трёх вариантов. TTL небольшой:
# нужен только на время обработки одной группы вариантов в рамках одного
# прогона, а не на весь процесс (иначе живой фетч мог бы отдавать данные
# многочасовой давности при PARSER_LIVE_FETCH).
_CATEGORY_CACHE_TTL_SECONDS = 600

# Витринные обозначения единиц у Мегастроя -> наши коды единиц из materials.json.
_UNIT_ALIASES = {
    "кг": "кг",
    "л": "л",
    "м2": "м²",
    "м²": "м²",
    "рул": "рулон",
    "рулон": "рулон",
    "шт": "шт",
    "м": "м",
}
_PRICE_UNIT_RE = re.compile(r"₽\s*/\s*(\S+)")

# Размерный блок в названии товара ("72х2500мм", "1292х193х7мм") — длина рейки/
# доски всегда наибольшее число (сечение — десятки мм, рейка/доска — сотни-тысячи).
_DIMENSION_MM_RE = re.compile(r"(\d+)\s*[xх]\s*(\d+)(?:\s*[xх]\s*(\d+))?\s*мм", re.IGNORECASE)

# Фасовка в названии товара ("(10л)", "25 кг", "280мл", "(9л)") — Мегастрой
# почти всегда пишет цену за упаковку целиком ("₽/шт"), а вес/объём даёт только
# в названии. "мл" проверяется до "л", иначе "л" внутри "мл" даёт ложное
# совпадение (граница слова спасает не всегда при переборе альтернатив).
_QUANTITY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(кг|мл|л)\b", re.IGNORECASE)


def _site_unit(price_text: str) -> str | None:
    match = _PRICE_UNIT_RE.search(price_text)
    if not match:
        return None
    return _UNIT_ALIASES.get(match.group(1).strip().lower())


def _length_m_from_title(title: str) -> Decimal | None:
    match = _DIMENSION_MM_RE.search(title)
    if not match:
        return None
    values = [int(g) for g in match.groups() if g]
    return Decimal(max(values)) / Decimal(1000)


def _quantity_from_title(title: str, unit: str) -> Decimal | None:
    for value_str, found_unit in _QUANTITY_RE.findall(title):
        if found_unit.lower() != unit:
            continue
        try:
            return Decimal(value_str.replace(",", "."))
        except InvalidOperation:
            continue
    return None


def _build_headers(url: str | None = None) -> dict[str, str]:
    # На megastroy стоит JS-challenge WAF (DDoS-Guard): голый requests ловит 403.
    # Способ 1 (ручной) — cookie hand-off: пользователь проходит проверку в браузере
    # и кладёт строку Cookie в MEGASTROY_COOKIE (целиком из DevTools → Network →
    # Request Headers → Cookie). При необходимости UA тоже можно переопределить
    # (MEGASTROY_UA) под свой браузер.
    # Способ 2 (beta) — MEGASTROY_HEADLESS=1: headless-браузер сам проходит
    # challenge и кэширует cookie на диске. Используется только если
    # MEGASTROY_COOKIE не задан руками явно.
    # Всё выключено по умолчанию → прежнее поведение (свой UA, без cookie) → 403 → seed.
    headers = dict(HEADERS)
    ua = os.environ.get("MEGASTROY_UA", "").strip()
    if ua:
        headers["User-Agent"] = ua
    cookie = os.environ.get("MEGASTROY_COOKIE", "").strip()
    if not cookie and settings.MEGASTROY_HEADLESS:
        cookie = headless_session.get_megastroy_cookie(
            url or "https://kazan.megastroy.com/", headers["User-Agent"]
        )
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _encode_url(url: str) -> str:
    # Кодирует кириллицу в URL (requests требует ASCII в query)
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    return base + "?" + quote(query, safe="=&[]")


def _is_real_href(href: str | None) -> bool:
    # Внутри карточки есть якоря-кнопки (сравнить/избранное/наличие) с href
    # "javascript:" или "#" — это не ссылка на товар. Берём только настоящие адреса.
    if not href:
        return False
    h = href.strip().lower()
    return not (h.startswith(("javascript:", "#", "mailto:", "tel:")) or h == "")


def _item_url(item, page_url: str) -> str | None:
    # Ссылка на карточку товара внутри одного .products-list__item.
    # В вёрстке Мегастроя карточка ведёт на /products/<id> якорем
    # .js-search-product-link; первыми же в DOM идут кнопки-заглушки с
    # href="javascript:" (сравнение, избранное) — их брать нельзя.
    link = item.select_one("a.js-search-product-link[href]")
    href = link.get("href") if link else None
    if not _is_real_href(href):
        # Класс мог измениться — берём первый якорь с настоящим адресом.
        href = next(
            (a.get("href") for a in item.select("a[href]") if _is_real_href(a.get("href"))),
            None,
        )
    if not _is_real_href(href):
        return None
    abs_url = urljoin(page_url, href.strip())
    return abs_url if abs_url.startswith(("http://", "https://")) else None


def _item_title(item) -> str:
    title_el = item.select_one(".products-list__content-title a")
    if not title_el:
        return ""
    return title_el.get("title") or title_el.get_text(strip=True)


def _parse_page(html: str, page_url: str) -> list[tuple[Decimal, str | None, str | None, str]]:
    # Достаёт со страницы кортежи (цена, ссылка на карточку, витринная единица, название).
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".products-list__item")
    results = []
    for item in items:
        price_el = item.select_one('[itemprop="price"]')
        if not price_el:
            continue
        content = price_el.get("content")
        if not content:
            continue
        try:
            value = Decimal(content)
        except Exception:
            continue
        if value <= 0:
            continue
        # Витринная единица напечатана текстом в том же блоке, что и meta-цена
        # ("179 ₽/шт", "399 ₽/м2") — meta-теги своего текста не дают.
        unit = _site_unit(price_el.parent.get_text(strip=True)) if price_el.parent else None
        results.append((value, _item_url(item, page_url), unit, _item_title(item)))
    return results


class MegastroyParser(BaseParser):
    source_name = "Мегастрой"

    def __init__(self):
        # Кэш сырых цен по urls категории (#341) — см. _CATEGORY_CACHE_TTL_SECONDS.
        # Инстанс — синглтон в registry.py и переживает весь процесс (в т.ч. live
        # API-путь), поэтому конкурентные запросы возможны; лок сериализует
        # проверку кэша и сетевой фетч, чтобы два запроса на одну категорию не
        # сходили в сеть дважды одновременно.
        self._raw_cache: dict[tuple[str, ...], tuple[float, list]] = {}
        self._raw_cache_lock = threading.Lock()

    def known_materials(self) -> list[str]:
        return list(CATEGORY_MAP.keys())

    def _fetch_raw_items(
        self, urls: tuple[str, ...], material_name: str
    ) -> list[tuple[Decimal, str | None, str | None, str]]:
        # Кортежи (цена, ссылка на карточку, витринная единица, название) со всех
        # категорий материала — плитка, например, размазана по двум разделам.
        # Вариантные материалы (эконом/премиум) шлют один и тот же urls — при
        # повторном вызове в пределах TTL отдаём уже скачанное, не ходя в сеть.
        with self._raw_cache_lock:
            cached = self._raw_cache.get(urls)
            if cached is not None:
                fetched_at, raw_items = cached
                if time.monotonic() - fetched_at < _CATEGORY_CACHE_TTL_SECONDS:
                    logger.info(
                        f"  Мегастрой '{material_name}': категория {urls[0]} из кэша "
                        f"({len(raw_items)} цен, без повторного фетча)"
                    )
                    return raw_items

            headers = _build_headers(_encode_url(urls[0]))
            raw_items: list[tuple[Decimal, str | None, str | None, str]] = []

            for base_url in urls:
                base_url = _encode_url(base_url)
                sep = "&" if "?" in base_url else "?"

                for page in range(1, MAX_PAGES + 1):
                    # Первую страницу берем без ?page (так устроен сайт),
                    # пагинацию добавляем только со 2-й
                    url = base_url if page == 1 else f"{base_url}{sep}page={page}"

                    time.sleep(REQUEST_DELAY)
                    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

                    if response.status_code == 404:
                        break
                    response.raise_for_status()

                    page_items = _parse_page(response.text, url)
                    if not page_items:
                        break

                    raw_items.extend(page_items)
                    logger.info(f"  Мегастрой '{material_name}' {base_url} стр.{page}: +{len(page_items)} цен")

            self._raw_cache[urls] = (time.monotonic(), raw_items)
            return raw_items

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Мегастроя для материала '{material_name}'")

        category = CATEGORY_MAP[material_name]
        raw_items = self._fetch_raw_items(category.urls, material_name)

        if not raw_items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

        # Третий элемент кортежа — package_size (#306): фасовка ЭТОГО конкретного
        # товара, извлечённая при нормализации цены, а не справочная. Для
        # site_unit-категорий (плитка/ламинат/обои) сайт не даёт отдельной
        # "цены за коробку" на странице категории — фасовку взять неоткуда,
        # остаётся None (fallback на статичный Material.package_size).
        items: list[tuple[Decimal, str | None, Decimal | None]]
        if category.site_unit is not None:
            # Категория смешивает разнородные позиции (замазка "₽/шт" в шпаклёвке,
            # добавки в мл в затирке) — отсекаем всё, чья витринная единица не
            # совпадает с ожидаемой (#277).
            items = [
                (price, url, None) for price, url, unit, _title in raw_items if unit == category.site_unit
            ]
        elif category.title_unit is not None:
            # Мегастрой у весовых/объёмных материалов всегда пишет цену за
            # упаковку целиком ("₽/шт") — вес/объём достаём из названия и
            # считаем базовую цену сами. qty — это и есть реальная фасовка
            # товара (сколько кг/л в упаковке), несём её дальше как package_size.
            items = []
            for price, url, _unit, title in raw_items:
                qty = _quantity_from_title(title, category.title_unit)
                if qty:
                    items.append((price / qty, url, qty))
        elif category.normalize_length_mm:
            # Плинтус продаётся рейкой ("72х2500мм") по цене за шт — приводим
            # к ₽/м делением на длину рейки из названия. Длина рейки — и есть
            # package_size (м на упаковку).
            items = []
            for price, url, _unit, title in raw_items:
                length_m = _length_m_from_title(title)
                if length_m:
                    items.append((price / length_m, url, length_m))
        else:
            items = [(price, url, None) for price, url, _unit, _title in raw_items]

        if not items:
            raise RuntimeError(
                f"Не найдено подходящих цен для '{material_name}' (единица/размер не распознаны)"
            )

        # Категория смешивает разнородные товары — отсекаем ценовые выбросы (#207),
        # иначе min/avg/max и товар-представитель (#197) считаются по всей категории.
        raw_count = len(items)
        items = filter_outliers(items, key=lambda it: it[0])
        if len(items) < raw_count:
            logger.info(
                f"  Мегастрой '{material_name}': отброшено выбросов "
                f"{raw_count - len(items)} из {raw_count}"
            )

        # Вариант по уровню комплектации (#331): нижняя/верхняя треть цен категории
        # вместо всей выборки — см. price_band_slice и docs/price-sources.md.
        if category.price_band:
            band_count = len(items)
            items = price_band_slice(items, category.price_band, key=lambda it: it[0])
            logger.info(
                f"  Мегастрой '{material_name}': price_band={category.price_band}, "
                f"{len(items)} из {band_count} цен"
            )

        all_prices = [price for price, _, _ in items]
        price_min = min(all_prices)
        price_max = max(all_prices)
        price_avg = Decimal(round(statistics.mean(all_prices)))

        # Источник — карточка товара, чья цена ближе всего к показанной (avg), как и
        # для работ (price_aggregator._combine_labor_prices). Товар без ссылки →
        # деградируем до URL категории, чтобы источник никогда не был пустым (#197).
        # package_size берём у ТОГО ЖЕ товара (#306) — иначе фасовка в смете и
        # фасовка на странице source_url могут не совпадать.
        representative = min(items, key=lambda it: abs(it[0] - price_avg))
        source_url = representative[1] or category.urls[0]
        package_size = representative[2]

        logger.info(
            f"Мегастрой: '{material_name}' — всего {len(all_prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}, source={source_url}"
        )

        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=source_url,
            package_size=package_size,
        )
