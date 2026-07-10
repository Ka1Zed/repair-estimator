import logging
import os
import statistics
import time
from decimal import Decimal
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import headless_session
from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice, DEFAULT_HEADERS, DEFAULT_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Карта: материал в БД -> URL категории. У Лемана нет отдельной категории только
# для потолочной краски (в отличие от Мегастроя с field142[]=для потолков) —
# оба материала временно указывают на одну и ту же общую категорию (#276).
_PAINT_CATEGORY_URL = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"
CATEGORY_MAP = {
    "Краска для стен": _PAINT_CATEGORY_URL,
    "Краска потолочная": _PAINT_CATEGORY_URL,
}

HEADERS = {**DEFAULT_HEADERS, "Accept": "text/html,application/xhtml+xml"}

REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT      # таймаут запроса, сек
REQUEST_DELAY = 1.0       # пауза между страницами, чтобы не долбить сайт
MAX_PAGES = 20            # защита от бесконечного цикла


def _build_headers(url: str | None = None) -> dict[str, str]:
    # По аналогии с megastroy_parser._build_headers: если сайт блокирует голый
    # requests, есть два пути обхода — ручной cookie hand-off (LEMAN_COOKIE) или
    # beta headless-харвестер (LEMAN_HEADLESS=1). Оба выключены по умолчанию.
    headers = dict(HEADERS)
    ua = os.environ.get("LEMAN_UA", "").strip()
    if ua:
        headers["User-Agent"] = ua
    cookie = os.environ.get("LEMAN_COOKIE", "").strip()
    if not cookie and settings.LEMAN_HEADLESS:
        cookie = headless_session.get_leman_cookie(
            url or "https://kazan.lemanapro.ru/", headers["User-Agent"]
        )
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _parse_page(html: str, page_url: str) -> list[tuple[Decimal, str | None]]:
    # Достаёт со страницы пары (цена, ссылка на карточку товара). Каждая карточка
    # в SSR-разметке Лемана рендерится дважды (мобильная/десктопная копия с
    # одинаковыми data-sl-product-id) — дедуплицируем, иначе цены задвоятся.
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select('[data-qa="products-list"] [data-sl-product-id]')
    results = []
    seen_ids: set[str] = set()
    for item in items:
        product_id = item.get("data-sl-product-id")
        if product_id in seen_ids:
            continue

        price_el = item.select_one('[data-testid="price-block-price"]')
        if not price_el:
            continue
        value = price_el.get("value")
        if not value:
            continue
        try:
            price = Decimal(value)
        except Exception:
            continue
        if price <= 0:
            continue

        link_el = item.select_one('a[data-qa="product-name"][href]')
        href = link_el.get("href") if link_el else None
        url = urljoin(page_url, href.strip()) if href else None

        seen_ids.add(product_id)
        results.append((price, url))
    return results


class LemanParser(BaseParser):
    source_name = "Леман"

    def known_materials(self) -> list[str]:
        return list(CATEGORY_MAP.keys())

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Лемана для материала '{material_name}'")

        base_url = CATEGORY_MAP[material_name]
        sep = "&" if "?" in base_url else "?"

        headers = _build_headers(base_url)
        items: list[tuple[Decimal, str | None]] = []

        for page in range(1, MAX_PAGES + 1):
            # Первая страница — без ?page (0-я страница сайта), со 2-й добавляем
            # ?page=1, ?page=2, ... (пагинация Лемана 0-индексирована).
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}{sep}page={page - 1}"

            time.sleep(REQUEST_DELAY)
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 404:
                break
            response.raise_for_status()

            page_items = _parse_page(response.text, url)
            if not page_items:
                # Останов по пустой странице, а не только по 404 — поведение
                # сайта на overflow-страницах не подтверждено живым прогоном.
                break

            items.extend(page_items)
            logger.info(f"  Леман '{material_name}' стр.{page}: +{len(page_items)} цен")

        if not items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

        raw_count = len(items)
        items = filter_outliers(items, key=lambda it: it[0])
        if len(items) < raw_count:
            logger.info(
                f"  Леман '{material_name}': отброшено выбросов "
                f"{raw_count - len(items)} из {raw_count}"
            )

        all_prices = [price for price, _ in items]
        price_min = min(all_prices)
        price_max = max(all_prices)
        price_avg = Decimal(round(statistics.mean(all_prices)))

        representative = min(items, key=lambda it: abs(it[0] - price_avg))
        source_url = representative[1] or CATEGORY_MAP[material_name]

        logger.info(
            f"Леман: '{material_name}' — всего {len(all_prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}, source={source_url}"
        )

        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=source_url,
        )
