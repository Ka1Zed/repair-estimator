import logging
import time
import statistics
from decimal import Decimal
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

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


def _encode_url(url: str) -> str:
    # Кодирует кириллицу в URL (requests требует ASCII в query)
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    return base + "?" + quote(query, safe="=&[]")


def _parse_page(html: str) -> list[Decimal]:
    # Достает все цены с одной страницы
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".products-list__item")
    prices = []
    for item in items:
        price_el = item.select_one('[itemprop="price"]')
        if not price_el:
            continue
        content = price_el.get("content")
        if not content:
            continue
        try:
            value = Decimal(content)
            if value > 0:
                prices.append(value)
        except Exception:
            continue
    return prices


class MegastroyParser(BaseParser):
    source_name = "Мегастрой"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Мегастроя для материала '{material_name}'")

        base_url = _encode_url(CATEGORY_MAP[material_name])
        sep = "&" if "?" in base_url else "?"

        all_prices: list[Decimal] = []

        for page in range(1, MAX_PAGES + 1):
            # Первую страницу берем без ?page (так устроен сайт),
            # пагинацию добавляем только со 2-й
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}{sep}page={page}"

            time.sleep(REQUEST_DELAY)
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

            if response.status_code == 404:
                break
            response.raise_for_status()

            page_prices = _parse_page(response.text)
            if not page_prices:
                break

            all_prices.extend(page_prices)
            logger.info(f"  Мегастрой '{material_name}' стр.{page}: +{len(page_prices)} цен")

        if not all_prices:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

        price_min = min(all_prices)
        price_max = max(all_prices)
        price_avg = Decimal(round(statistics.mean(all_prices)))

        logger.info(
            f"Мегастрой: '{material_name}' — всего {len(all_prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}"
        )

        return ParsedPrice(price_min=price_min, price_avg=price_avg, price_max=price_max)