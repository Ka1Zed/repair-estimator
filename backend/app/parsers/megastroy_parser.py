import logging
import os
import statistics
import time
from decimal import Decimal
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import headless_session
from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)

# Карта: материал в БД -> базовый URL категории (с нужным фильтром по назначению)
CATEGORY_MAP = {
    "Краска для стен": "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",
    "Краска потолочная": "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot?field142[]=для потолков",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

REQUEST_TIMEOUT = 10      # таймаут запроса, сек
REQUEST_DELAY = 1.0       # пауза между страницами, чтобы не долбить сайт
MAX_PAGES = 20            # защита от бесконечного цикла


def _build_headers(url: str | None = None) -> dict[str, str]:
    # На megastroy стоит JS-challenge WAF (DDoS-Guard): голый requests ловит 403.
    # Способ 1 (ручной) — cookie hand-off: пользователь проходит проверку в браузере
    # и кладёт строку Cookie в MEGASTROY_COOKIE (целиком из DevTools → Network →
    # Request Headers → Cookie). При необходимости UA тоже можно переопределить
    # (MEGASTROY_UA) под свой браузер.
    # Способ 2 (beta) — MEGASTROY_HEADLESS=1: headless Playwright сам проходит
    # challenge и кэширует cookie на диске (см.
    # plans/2026-06-30-beta-headless-parser.md). Используется только если
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


def _parse_page(html: str, page_url: str) -> list[tuple[Decimal, str | None]]:
    # Достаёт со страницы пары (цена, ссылка на карточку товара).
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
        if value > 0:
            results.append((value, _item_url(item, page_url)))
    return results


class MegastroyParser(BaseParser):
    source_name = "Мегастрой"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Мегастроя для материала '{material_name}'")

        base_url = _encode_url(CATEGORY_MAP[material_name])
        sep = "&" if "?" in base_url else "?"

        headers = _build_headers(base_url)
        # Пары (цена, ссылка на карточку) — ссылка нужна, чтобы в смете показать
        # источником конкретный товар, а не общую категорию (#197).
        items: list[tuple[Decimal, str | None]] = []

        for page in range(1, MAX_PAGES + 1):
            # Первую страницу берем без ?page (так устроен сайт),
            # пагинацию добавляем только со 2-й
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}{sep}page={page}"

            time.sleep(REQUEST_DELAY)
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 404:
                break
            response.raise_for_status()

            page_items = _parse_page(response.text, url)
            if not page_items:
                break

            items.extend(page_items)
            logger.info(f"  Мегастрой '{material_name}' стр.{page}: +{len(page_items)} цен")

        if not items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

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
        source_url = representative[1] or CATEGORY_MAP[material_name]

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