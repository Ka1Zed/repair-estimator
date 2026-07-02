import logging
import re
import statistics
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParsedPrice
from app.parsers.labor_table_parser import LABOR_SERVICE_MAP, _matches

logger = logging.getLogger(__name__)

PRICE_URL = "https://rembrigada116.ru/price"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}
REQUEST_TIMEOUT = 10

# Правила отбора строк прайса общие для всех парсеров работ — единый источник
# LABOR_SERVICE_MAP в labor_table_parser (чтобы карты не расходились).


def _parse_price(text: str) -> Decimal | None:
    # 'от 1590' / '1 590 руб' -> Decimal(1590). Возвращает None, если числа нет
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return Decimal(digits)


class RembrigadaParser(BaseParser):
    source_name = "company_price"
    # rembrigada116.ru — казанская компания: помимо базового (безрегионального)
    # прогона парсер участвует в региональном как второй источник по Казани.
    region = "Казань"

    def __init__(self):
        self._rows_cache = None  # таблицу качаем один раз на все услуги

    def _load_rows(self) -> list[tuple[str, Decimal]]:
        if self._rows_cache is not None:
            return self._rows_cache
        resp = requests.get(PRICE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for tr in soup.select("tr"):
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if len(cells) >= 3:
                name = cells[0].lower()
                price = _parse_price(cells[-1])
                if price and price > 0:
                    rows.append((name, price))
        self._rows_cache = rows
        return rows

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in LABOR_SERVICE_MAP:
            raise ValueError(f"Нет правил для услуги '{material_name}'")

        rule = LABOR_SERVICE_MAP[material_name]
        rows = self._load_rows()

        prices = [price for (name, price) in rows if _matches(name, rule)]

        if not prices:
            raise RuntimeError(f"Не найдено строк прайса для '{material_name}'")

        price_min = min(prices)
        price_max = max(prices)
        price_avg = Decimal(round(statistics.mean(prices)))

        logger.info(
            f"company_price: '{material_name}' — {len(prices)} строк, "
            f"min={price_min}, avg={price_avg}, max={price_max}"
        )
        # Все услуги берём из одного прайс-листа — ссылка на него общая.
        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=PRICE_URL,
        )