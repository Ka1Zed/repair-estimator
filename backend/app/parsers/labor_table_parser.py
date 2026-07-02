import logging
import re
import statistics
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}
REQUEST_TIMEOUT = 10

# Цена работы не бывает меньше этого порога. Нужен, чтобы reversed-скан строки не
# принял ячейку-единицу за цену: 'м2'/'м3' содержат цифру и парсятся в 2/3.
MIN_PRICE = Decimal(10)

# Карта: наша услуга -> правила отбора строк прайса.
#   include_all — все эти слова должны встретиться в названии
#   include_any — хотя бы одно из этих (если список не пуст)
#   exclude     — ни одного из этих не должно быть
# Подход переиспользован из RembrigadaParser; словарь расширен под верстку
# московского и питерского прайсов (напр. «Настил ламината», «шпатлёвка» с ё).
LABOR_SERVICE_MAP = {
    "Покраска стен": {
        "include_all": ["стен"],
        "include_any": ["окраск", "покраск"],
        "exclude": ["демонтаж", "очистк", "багет", "откос", "короб", "распылител",
                    "колонн", "металлоконструк", "шпатлевка", "шпаклевка", "шпатлёвка",
                    "ошкуривание", "шлифовк", "грунтовк", "радиатор", "галтел",
                    "обоями", "оклейк"],
    },
    "Покраска потолка": {
        "include_all": ["потолк"],
        "include_any": ["окраск", "покраск"],
        "exclude": ["демонтаж", "очистк", "багет", "плинтус", "распылител",
                    "шпатлевка", "шпаклевка", "шпатлёвка", "ошкуривание", "шлифовк",
                    "грунтовк", "плитк", "галтел"],
    },
    "Шпаклевка стен": {
        "include_all": ["стен"],
        # «шпаклеван»/«шпатлеван» — казанский прайс пишет «базовое шпаклевание стен»
        "include_any": ["шпатлевка", "шпаклевка", "шпатлёвка", "шпаклеван", "шпатлеван"],
        "exclude": ["демонтаж", "очистк", "откос", "короб", "потолк", "галтел",
                    "армирован"],
    },
    "Укладка ламината": {
        "include_all": ["ламинат"],
        "include_any": ["укладк", "настил"],
        "exclude": ["разборк", "демонтаж"],
    },
    "Укладка плитки": {
        "include_all": ["плитк"],
        "include_any": ["облицовк", "укладк"],
        "exclude": ["демонтаж", "расчистк", "затирк", "рез", "уголк", "очистк",
                    "потолочн", "потолк", "сбивк", "фартук", "короб"],
    },
    "Электромонтаж": {
        "include_all": [],
        "include_any": ["розетк", "выключател", "электр"],
        # Услуга считается «за точку» (docs/estimation-rules.md) — исключаем
        # крупные работы не про точки: щиты, котлы, зарядные станции и т.п.
        "exclude": ["демонтаж", "домофон", "звонок", "теплого пола", "сверление",
                    "водогре", "водонагрева", "конвектор", "электрощит", "котл",
                    "электромобил",
                    "генератор", "расходомер", "гидромассаж", "кондиционер",
                    "сплит"],
    },
    "Сантехнические работы": {
        "include_all": [],
        "include_any": ["смесител", "унитаз", "установка бачк"],
        "exclude": ["демонтаж", "демонтах"],
    },
}


def _parse_price(text: str) -> Decimal | None:
    '''
    'от 1 590 руб' -> 1590, '700/1100' -> 700. Берём первое число; пробел
    считаем разделителем тысяч. Возвращает None, если числа нет.
    '''
    digits = re.sub(r"\s", "", text)
    match = re.search(r"\d+", digits)
    if not match:
        return None
    return Decimal(match.group())


def _matches(name: str, rule: dict) -> bool:
    if any(w in name for w in rule["exclude"]):
        return False
    if rule["include_all"] and not all(w in name for w in rule["include_all"]):
        return False
    if rule["include_any"] and not any(w in name for w in rule["include_any"]):
        return False
    return True


class LaborTableParser(BaseParser):
    '''
    Базовый парсер прайса отделочных работ из HTML-таблицы.
    Подкласс задаёт PRICE_URL, source_name и region; остальное общее.

    Вёрстка прайсов разная: строка таблицы = ячейки, среди которых есть название
    работы и цена. Имя берём из первой ячейки с буквами (у части сайтов первая
    ячейка пустая), цену — из последней ячейки с числом >= MIN_PRICE (у части
    сайтов последняя ячейка — единица «м2», а цена в предпоследней; из
    «600 руб. 534 руб.» берём первую — цену без скидки). Услуги сопоставляем с
    LABOR_SERVICE_MAP по include/exclude словам, как в RembrigadaParser.
    '''

    # Регион, к которому относятся цены сайта (пишется в LaborPrice.region).
    region: str

    # Таймаут запроса; подкласс может увеличить для тяжёлых страниц.
    request_timeout = REQUEST_TIMEOUT

    def __init__(self):
        self._rows_cache = None  # таблицы качаем один раз на все услуги

    def _page_urls(self) -> list[str]:
        # По умолчанию прайс на одной странице; подкласс может вернуть несколько
        # (у части сайтов электрика/сантехника опубликованы отдельными страницами).
        return [self.PRICE_URL]

    def _clean_name(self, name: str) -> str:
        # Хук для подкласса: убрать из названия работы мусор конкретной вёрстки
        # (например, раскрытое описание состава работ), чтобы include/exclude
        # слова матчились по названию, а не по описанию.
        return name

    def _get_html(self, url: str) -> str:
        resp = requests.get(url, headers=HEADERS, timeout=self.request_timeout)
        resp.raise_for_status()
        return resp.text

    def _load_rows(self) -> list[tuple[str, Decimal, str]]:
        if self._rows_cache is not None:
            return self._rows_cache
        rows = []
        for url in self._page_urls():
            try:
                html = self._get_html(url)
            except requests.RequestException:
                # Одна недоступная страница не должна ронять остальные: услуги
                # без строк уйдут в RuntimeError -> fallback на seed (#159).
                logger.warning(f"{self.source_name}: страница {url} недоступна")
                continue
            soup = BeautifulSoup(html, "html.parser")
            for tr in soup.select("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
                if len(cells) < 2:
                    continue
                name = next((c for c in cells if re.search(r"[А-Яа-яA-Za-z]", c)), None)
                if not name:
                    continue
                # Цена — последняя ячейка с числом >= MIN_PRICE (последней может
                # быть единица измерения «м2» -> 2, её пропускаем).
                price = None
                for cell in reversed(cells):
                    value = _parse_price(cell)
                    if value is not None and value >= MIN_PRICE:
                        price = value
                        break
                if price:
                    rows.append((self._clean_name(name.lower()), price, url))
        self._rows_cache = rows
        return rows

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in LABOR_SERVICE_MAP:
            raise ValueError(f"Нет правил для услуги '{material_name}'")

        rule = LABOR_SERVICE_MAP[material_name]
        rows = self._load_rows()

        matched = [(price, url) for (name, price, url) in rows if _matches(name, rule)]

        if not matched:
            raise RuntimeError(f"Не найдено строк прайса для '{material_name}'")

        prices = [price for (price, _) in matched]
        price_min = min(prices)
        price_max = max(prices)
        price_avg = Decimal(round(statistics.mean(prices)))

        logger.info(
            f"{self.source_name}: '{material_name}' — {len(prices)} строк, "
            f"min={price_min}, avg={price_avg}, max={price_max}"
        )
        # Ссылка — страница прайса, на которой нашлась услуга.
        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=matched[0][1],
        )
