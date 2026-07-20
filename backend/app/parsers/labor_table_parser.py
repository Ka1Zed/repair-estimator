import logging
import re
import statistics
from decimal import Decimal

import requests
from bs4 import BeautifulSoup

from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice, DEFAULT_HEADERS, DEFAULT_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

HEADERS = DEFAULT_HEADERS
REQUEST_TIMEOUT = DEFAULT_REQUEST_TIMEOUT

# Цена работы не бывает меньше этого порога. Нужен, чтобы reversed-скан строки не
# принял ячейку-единицу за цену: 'м2'/'м3' содержат цифру и парсятся в 2/3.
MIN_PRICE = Decimal(10)

# Карта: наша услуга -> правила отбора строк прайса.
#   include_all  — все эти слова должны встретиться в названии
#   include_any  — хотя бы одно из этих (если список не пуст)
#   include_any2 — второй, независимый OR-набор (если список не пуст); нужен, когда
#                  фильтр — это AND двух OR-групп («слово-действие» И «слово-предмет»,
#                  напр. демонтаж/разборка + стены/перегородки, #401), а include_all
#                  такое не выражает (это AND одиночных слов, не групп)
#   exclude      — ни одного из этих не должно быть
#   unit         — каталожная единица услуги (LaborService.unit, см.
#                  db/seed_data/labor_services.json); строка прайса без совпадающей
#                  единицы отсекается (см. _normalize_unit/_unit_matches, #391)
# Единый словарь правил для всех парсеров работ (в т.ч. RembrigadaParser) —
# чтобы карты не расходились. Расширен под вёрстку московского, питерского и
# казанского прайсов (напр. «Настил ламината», «шпатлёвка» с ё, «шпаклевание»).
LABOR_SERVICE_MAP = {
    "Покраска стен": {
        "include_all": ["стен"],
        "include_any": ["окраск", "покраск"],
        "exclude": ["демонтаж", "очистк", "багет", "откос", "короб", "распылител",
                    "колонн", "металлоконструк", "шпатлевка", "шпаклевка", "шпатлёвка",
                    "ошкуривание", "шлифовк", "грунтовк", "радиатор", "галтел",
                    "обоями", "оклейк"],
        "unit": "м²",
    },
    "Покраска потолка": {
        "include_all": ["потолк"],
        "include_any": ["окраск", "покраск"],
        "exclude": ["демонтаж", "очистк", "багет", "плинтус", "распылител",
                    "шпатлевка", "шпаклевка", "шпатлёвка", "ошкуривание", "шлифовк",
                    "грунтовк", "плитк", "галтел"],
        "unit": "м²",
    },
    "Шпаклевка стен": {
        "include_all": ["стен"],
        # «шпаклеван»/«шпатлеван» — казанский прайс пишет «базовое шпаклевание стен»
        "include_any": ["шпатлевка", "шпаклевка", "шпатлёвка", "шпаклеван", "шпатлеван"],
        "exclude": ["демонтаж", "очистк", "откос", "короб", "потолк", "галтел",
                    "армирован"],
        "unit": "м²",
    },
    "Укладка ламината": {
        "include_all": ["ламинат"],
        "include_any": ["укладк", "настил"],
        "exclude": ["разборк", "демонтаж"],
        "unit": "м²",
    },
    "Укладка плитки": {
        "include_all": ["плитк"],
        "include_any": ["облицовк", "укладк"],
        "exclude": ["демонтаж", "расчистк", "затирк", "рез", "уголк", "очистк",
                    "потолочн", "потолк", "сбивк", "фартук", "короб"],
        "unit": "м²",
    },
    "Электромонтаж": {
        "include_all": [],
        "include_any": ["розетк", "выключател", "электр"],
        # Услуга считается «за точку» (docs/estimation-rules.md) — исключаем
        # крупные работы не про точки: щиты, котлы, зарядные станции и т.п.
        # "щит" (не "электрощит") — реальная формулировка на сайтах «электрического
        # щита», «электрощита» не встречается как цельное слово (#391).
        "exclude": ["демонтаж", "домофон", "звонок", "теплого пола", "сверление",
                    "водогре", "водонагрева", "конвектор", "щит", "котл",
                    "электромобил",
                    "генератор", "расходомер", "гидромассаж", "кондиционер",
                    "сплит"],
        "unit": "точка",
    },
    # Сантехника (#401): раньше одна услуга «Сантехнические работы» мешала
    # установку бачка, смесителя и напольного унитаза в сборе в одну вилку —
    # эти операции отличаются по цене в 2-3 раза (разный объём работы за «точку»).
    # «Замена»/«демонтаж» — операции ремонта/демонтажа, не установки — исключаем
    # везде; узел/клапан/группа/котёл/тёплый пол — смесительный узел отопления
    # (омоним по корню «смесит-», не сантехника), гигиенический душ/инсталляция/
    # подвесной унитаз — другие по составу и цене изделия, оставлены вне скоупа.
    "Установка смесителя": {
        "include_all": [],
        "include_any": ["установ", "монтаж", "подключ"],
        "include_any2": ["смесител"],
        "exclude": ["демонтаж", "демонтах", "замена", "заменит", "регулировк",
                    "ремонт", "клапан", "групп", "котл", "тёплого пола",
                    "инсталляц", "гигиенич", "насосн", "панел", "колонк"],
        "unit": "точка",
    },
    "Установка унитаза": {
        "include_all": [],
        "include_any": ["установ", "монтаж"],
        "include_any2": ["унитаз"],
        # "бачк" — исключаем, иначе «Установка бачка унитаза» (своя, более дешёвая
        # услуга) попадает сюда же и тянет вилку вниз (#401).
        "exclude": ["демонтаж", "демонтах", "замена", "регулировк", "ремонт",
                    "устранени", "засор", "крышк", "биде-приставк", "инсталляц",
                    "подвесн", "насосн", "бачк"],
        "unit": "точка",
    },
    "Установка бачка унитаза": {
        "include_all": [],
        "include_any": ["установ", "монтаж"],
        "include_any2": ["бачк"],
        "exclude": ["демонтаж", "демонтах", "замена", "регулировк", "ремонт",
                    "насосн"],
        "unit": "точка",
    },
    # Черновые работы (#190): раньше эти строки выкидывались exclude-списками
    # финишных услуг подчистую. Теперь роутим их в отдельные услуги, чтобы
    # черновой этап попадал в смету (финиш по-прежнему их исключает — см. выше).
    #
    # «Демонтаж» (#401): одна услуга мешала лёгкий демонтаж поверхностей
    # (линолеум, ковролин ≈ 80-220 ₽/м²) и капитальный (кирпич, бетон ≈
    # 400-3000+ ₽/м²) — разброс ×10-40 не отсекался фильтром выбросов (Тьюки),
    # т.к. это не выбросы, а полноценные разные подвыборки. Разбито по типу
    # операции; unit «м²» у всех трёх (штучные/объёмные строки уже отсекает
    # _unit_matches).
    "Демонтаж напольного покрытия": {
        "include_all": [],
        "include_any": ["демонтаж", "демонтах", "разборк", "снос", "снят"],
        "include_any2": ["линолеум", "ламинат", "паркет", "ковролин", "дсп",
                          "двп", "фанер"],
        "exclude": ["стен", "потолк", "плинтус"],
        "unit": "м²",
    },
    "Демонтаж стен и перегородок": {
        "include_all": [],
        "include_any": ["демонтаж", "демонтах", "разборк", "снос"],
        "include_any2": ["стен", "перегородк", "фальшстен"],
        "exclude": ["потолк", "плинтус", "откос", "плитк", "штукатурк", "панел"],
        "unit": "м²",
    },
    "Демонтаж стяжки": {
        "include_all": [],
        "include_any": ["демонтаж", "демонтах", "разборк", "снос"],
        "include_any2": ["стяжк"],
        "exclude": [],
        "unit": "м²",
    },
    "Выравнивание стен": {
        "include_all": ["стен"],
        # штукатурка/выравнивание стен под финиш; не декоративка, не откосы и не
        # снятие старой штукатурки («отбивка» — демонтажная операция, не финиш, #391)
        "include_any": ["выравниван", "штукатур"],
        "exclude": ["демонтаж", "потолк", "откос", "декоратив", "отбивк"],
        "unit": "м²",
    },
    "Стяжка пола": {
        "include_all": [],
        "include_any": ["стяжк", "наливн пол", "выравнивание пол"],
        "exclude": ["демонтаж"],
        "unit": "м²",
    },
    "Гидроизоляция": {
        "include_all": [],
        "include_any": ["гидроизол"],
        "exclude": ["демонтаж"],
        "unit": "м²",
    },
    "Грунтование": {
        "include_all": [],
        "include_any": ["грунтован", "грунтовк"],
        # "гидроизол" — комбинированная строка с чужой услугой (у гидроизоляции
        # своя услуга «Гидроизоляция»), не грунтовка (#391).
        "exclude": ["демонтаж", "потолк", "гидроизол"],
        "unit": "м²",
    },
}

# Группы единиц, которые сайты пишут по-разному, но означают одно и то же с точки
# зрения отбора строк прайса. "точка" — наша каталожная единица для электрики/
# сантехники (docs/estimation-rules.md), но ни один прайс не пишет буквально
# "точка" — сайты считают такие позиции штучно ("шт"), поэтому группируем их
# вместе (#391).
_UNIT_EQUIVALENT_GROUPS = [{"шт", "точка"}]


def _unit_matches(row_unit: str | None, expected_unit: str) -> bool:
    # Единицу строки не распознали — не отсеиваем (подстраховка на случай вёрстки
    # без чистой ячейки-единицы измерения, старое поведение).
    if row_unit is None:
        return True
    if row_unit == expected_unit:
        return True
    return any(
        row_unit in group and expected_unit in group for group in _UNIT_EQUIVALENT_GROUPS
    )


# Единицу "м3"/"куб.м" намеренно не сводим к "м²" — объёмная работа (демонтаж
# монолитных конструкций и т.п.) не сопоставима по цене с квадратным метром (#391).
_UNIT_PATTERNS = [
    (re.compile(r"куб\.?\s?м|м\s*3\b|м³", re.I), "м³"),
    (re.compile(r"кв\.?\s?м|м\s*2\b|m2|м\s*²|м²", re.I), "м²"),
    (re.compile(r"пог\.?\s?м|п\.?\s?м\.?|м\s*/\s*п|мп\b|м\.п", re.I), "м"),
    (re.compile(r"компл", re.I), "шт"),
    (re.compile(r"\bшт\b", re.I), "шт"),
    (re.compile(r"\bточ", re.I), "точка"),
]


def _normalize_unit(text: str) -> str | None:
    '''Сводит сырую ячейку единицы измерения ("кв.м.", "м2", "п.м.", "шт" и т.п.)
    к одной из каталожных единиц (docs: labor_services.json). Нераспознанный текст
    (например, само название работы) -> None.'''
    stripped = text.strip()
    if not stripped:
        return None
    for pattern, normalized in _UNIT_PATTERNS:
        if pattern.search(stripped):
            return normalized
    # Голое "м" (без "2"/"3"/приставок) — линейный метр (напр. штробление, кабель).
    if re.fullmatch(r"м\.?", stripped, re.I):
        return "м"
    return None


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
    # "дополнительно" — доплата/дельта к другой строке прайса (напр. "укладка по
    # диагонали, дополнительно к стоимости..."), а не цена самостоятельной операции.
    # Отсекаем глобально, до правил конкретной услуги (#391).
    if "дополнительно" in name:
        return False
    if any(w in name for w in rule["exclude"]):
        return False
    if rule["include_all"] and not all(w in name for w in rule["include_all"]):
        return False
    if rule["include_any"] and not any(w in name for w in rule["include_any"]):
        return False
    include_any2 = rule.get("include_any2")
    if include_any2 and not any(w in name for w in include_any2):
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

    def _load_rows(self) -> list[tuple[str, Decimal, str, str | None]]:
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
                name_idx = next(
                    (i for i, c in enumerate(cells) if re.search(r"[А-Яа-яA-Za-z]", c)), None
                )
                if name_idx is None:
                    continue
                # Цена — последняя ячейка с числом >= MIN_PRICE (последней может
                # быть единица измерения «м2» -> 2, её пропускаем).
                price_idx, price = None, None
                for i in range(len(cells) - 1, -1, -1):
                    value = _parse_price(cells[i])
                    if value is not None and value >= MIN_PRICE:
                        price_idx, price = i, value
                        break
                if not price:
                    continue
                # Единица — первая из оставшихся ячеек (не имя, не цена), которую
                # удалось распознать (#391); не нашли -> None, старое поведение.
                unit = next(
                    (u for i, c in enumerate(cells)
                     if i not in (name_idx, price_idx)
                     and (u := _normalize_unit(c)) is not None),
                    None,
                )
                rows.append((self._clean_name(cells[name_idx].lower()), price, url, unit))
        self._rows_cache = rows
        return rows

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in LABOR_SERVICE_MAP:
            raise ValueError(f"Нет правил для услуги '{material_name}'")

        rule = LABOR_SERVICE_MAP[material_name]
        rows = self._load_rows()

        matched = [
            (price, url) for (name, price, url, unit) in rows
            if _matches(name, rule) and _unit_matches(unit, rule["unit"])
        ]

        if not matched:
            raise RuntimeError(f"Не найдено строк прайса для '{material_name}'")

        # Отсекаем ценовые выбросы (#242) до min/avg/max и до выбора source_url,
        # чтобы вилка считалась по «телу» выборки, а ссылка не вела на выброс.
        raw_count = len(matched)
        matched = filter_outliers(matched, key=lambda it: it[0])
        if len(matched) < raw_count:
            logger.info(
                f"{self.source_name}: '{material_name}' — отброшено выбросов "
                f"{raw_count - len(matched)} из {raw_count}"
            )

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
