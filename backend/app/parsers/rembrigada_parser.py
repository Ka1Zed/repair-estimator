import logging
import statistics
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParsedPrice, DEFAULT_HEADERS, DEFAULT_REQUEST_TIMEOUT
from app.parsers._stats import filter_outliers
from app.parsers.labor_table_parser import (
    LABOR_SERVICE_MAP,
    _matches,
    _normalize_unit,
    _parse_price,
    _unit_matches,
)

logger = logging.getLogger(__name__)

PRICE_URL = "https://rembrigada116.ru/price"

HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT

# Правила отбора строк прайса общие для всех парсеров работ — единый источник
# LABOR_SERVICE_MAP в labor_table_parser (чтобы карты не расходились).
# _parse_price тоже общий с labor_table_parser (была своя реализация, но она
# трактовала "700/1100" как 7001100 вместо 700 — баг, не просто дубль, #278).


class RembrigadaParser(BaseParser):
    source_name = "company_price"
    # rembrigada116.ru — казанская компания: помимо базового (безрегионального)
    # прогона парсер участвует в региональном как второй источник по Казани.
    region = "Казань"

    def __init__(self):
        self._rows_cache = None  # таблицу качаем один раз на все услуги

    def _load_rows(self) -> list[tuple[str, Decimal, str | None]]:
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
                    # Единица — первая из оставшихся ячеек (не имя, не цена),
                    # которую удалось распознать (#391, см. labor_table_parser).
                    unit = next(
                        (u for i, c in enumerate(cells)
                         if i not in (0, len(cells) - 1)
                         and (u := _normalize_unit(c)) is not None),
                        None,
                    )
                    rows.append((name, price, unit))
        self._rows_cache = rows
        return rows

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in LABOR_SERVICE_MAP:
            raise ValueError(f"Нет правил для услуги '{material_name}'")

        rule = LABOR_SERVICE_MAP[material_name]
        rows = self._load_rows()

        prices = [
            price for (name, price, unit) in rows
            if _matches(name, rule) and _unit_matches(unit, rule["unit"])
        ]

        if not prices:
            raise RuntimeError(f"Не найдено строк прайса для '{material_name}'")

        # Отсекаем ценовые выбросы (#242) до расчёта вилки — тот же хелпер, что и у
        # LaborTableParser, чтобы поведение парсеров работ не расходилось.
        raw_count = len(prices)
        prices = filter_outliers(prices)
        if len(prices) < raw_count:
            logger.info(
                f"company_price: '{material_name}' — отброшено выбросов "
                f"{raw_count - len(prices)} из {raw_count}"
            )

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