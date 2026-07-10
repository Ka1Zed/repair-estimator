import logging
import os
import re
import statistics
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import headless_session
from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice, DEFAULT_HEADERS, DEFAULT_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaterialCategory:
    # Одна или несколько категорий Мегастроя, откуда берём цены материала
    # (плитка размазана по "керамогранит" и "керамическая плитка", #277).
    urls: tuple[str, ...]
    # Мегастрой сам приводит цену к "витринной единице" конкретного товара и
    # пишет её текстом рядом с ценой ("179 ₽/шт", "399 ₽/м2") — категория при
    # этом мешает разнородные позиции (замазка "₽/шт" в разделе шпаклёвки,
    # добавки к затирке в мл). Указываем ожидаемую единицу — не совпало,
    # позиция отбрасывается. None — не фильтровать (краска, старое поведение).
    site_unit: str | None = None
    # Плинтус продаётся поштучно (рейка фикс. длины, витринная единица "шт"),
    # а наша база — метр: делим цену на длину, извлечённую из названия товара.
    normalize_length: bool = False


def _cat(url: str, site_unit: str | None = None, normalize_length: bool = False) -> MaterialCategory:
    return MaterialCategory(urls=(url,), site_unit=site_unit, normalize_length=normalize_length)


_SHPAKLEVKA = "https://kazan.megastroy.com/catalog/shpaklevka"

# Карта: материал в БД -> категория(и) Мегастроя (Казань) с фильтром, где нужен.
CATEGORY_MAP: dict[str, MaterialCategory] = {
    "Краска для стен": _cat("https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot"),
    "Краска потолочная": _cat(
        "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot?field142[]=для потолков"
    ),
    "Шпаклевка стартовая": _cat(
        f"{_SHPAKLEVKA}?field206[]=для заделки щелей, выбоин, трещин", site_unit="кг"
    ),
    "Шпаклевка финишная": _cat(
        f"{_SHPAKLEVKA}?field206[]=под окраску и оклейку обоями", site_unit="кг"
    ),
    "Грунтовка": _cat("https://kazan.megastroy.com/catalog/grunty", site_unit="л"),
    "Плиточный клей": _cat("https://kazan.megastroy.com/catalog/kley-dlya-plitki-2", site_unit="кг"),
    "Затирка": _cat("https://kazan.megastroy.com/catalog/zatirki-dlya-plitki", site_unit="кг"),
    "Плитка": MaterialCategory(
        urls=(
            "https://kazan.megastroy.com/catalog/keramogranit",
            "https://kazan.megastroy.com/catalog/keramicheskaya-plitka",
        ),
        site_unit="м²",
    ),
    "Ламинат": _cat("https://kazan.megastroy.com/catalog/laminat", site_unit="м²"),
    "Обои": _cat("https://kazan.megastroy.com/catalog/dekorativnye-oboi", site_unit="рулон"),
    "Плинтус": _cat(
        "https://kazan.megastroy.com/catalog/plintusy", site_unit="шт", normalize_length=True
    ),
}

# Расширяет DEFAULT_HEADERS собственным Accept — не чистый дубль (#278).
HEADERS = {**DEFAULT_HEADERS, "Accept": "text/html,application/xhtml+xml"}

REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT      # таймаут запроса, сек
REQUEST_DELAY = 1.0       # пауза между страницами, чтобы не долбить сайт
MAX_PAGES = 20            # защита от бесконечного цикла

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

    def known_materials(self) -> list[str]:
        return list(CATEGORY_MAP.keys())

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Мегастроя для материала '{material_name}'")

        category = CATEGORY_MAP[material_name]
        headers = _build_headers(_encode_url(category.urls[0]))

        # Кортежи (цена, ссылка на карточку, витринная единица, название) со всех
        # категорий материала — плитка, например, размазана по двум разделам.
        raw_items: list[tuple[Decimal, str | None, str | None, str]] = []

        for base_url in category.urls:
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

        if not raw_items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

        # Отсекаем позиции с чужой витринной единицей — категория мешает разное
        # (замазка "₽/шт" в шпаклёвке, добавки к затирке в мл, #277).
        if category.site_unit is not None:
            raw_items = [it for it in raw_items if it[2] == category.site_unit]

        if category.normalize_length:
            # Плинтус продаётся рейкой ("72х2500мм") по цене за шт — приводим
            # к ₽/м делением на длину рейки из названия.
            items: list[tuple[Decimal, str | None]] = []
            for price, url, _unit, title in raw_items:
                length_m = _length_m_from_title(title)
                if length_m:
                    items.append((price / length_m, url))
        else:
            items = [(price, url) for price, url, _unit, _title in raw_items]

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

        all_prices = [price for price, _ in items]
        price_min = min(all_prices)
        price_max = max(all_prices)
        price_avg = Decimal(round(statistics.mean(all_prices)))

        # Источник — карточка товара, чья цена ближе всего к показанной (avg), как и
        # для работ (price_aggregator._combine_labor_prices). Товар без ссылки →
        # деградируем до URL категории, чтобы источник никогда не был пустым (#197).
        representative = min(items, key=lambda it: abs(it[0] - price_avg))
        source_url = representative[1] or category.urls[0]

        logger.info(
            f"Мегастрой: '{material_name}' — всего {len(all_prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}, source={source_url}"
        )

        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=source_url,
        )
