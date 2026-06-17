import logging
import time
import statistics
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)

# Карта: материал в БД -> URL категории на Мегастрое
CATEGORY_MAP = {
    "Краска для стен": "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",
    "Краска потолочная": "https://kazan.megastroy.com/catalog/kraski-dlya-vnutrennih-rabot",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

REQUEST_TIMEOUT = 10          # таймаут запроса, сек
REQUEST_DELAY = 1.0           # пауза между запросами, чтобы не долбить сайт


class MegastroyParser(BaseParser):
    source_name = "Мегастрой"

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Мегастроя для материала '{material_name}'")

        url = CATEGORY_MAP[material_name]

        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select(".products-list__item")
        if not items:
            raise RuntimeError("Каталог не найден (возможно, урезанная страница)")

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

        if not prices:
            raise RuntimeError(f"Не найдено цен для '{material_name}'")

        price_min = min(prices)
        price_max = max(prices)
        price_avg = Decimal(round(statistics.mean(prices)))

        logger.info(
            f"Мегастрой: '{material_name}' — {len(prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}"
        )

        return ParsedPrice(price_min=price_min, price_avg=price_avg, price_max=price_max)