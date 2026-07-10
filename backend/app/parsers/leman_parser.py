import logging
import re
import statistics
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import leman_browser
from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnitSpec:
    # Леман показывает у каждого товара до двух ценовых блоков: основной
    # (price-block-price, обычно за упаковку/шт.) и вторичный normализованный
    # (price-block-unitprice, напр. "50.4 ₽/кг"), а для товаров вроде плитки/
    # ламината — наоборот, основной блок уже за м², а вторичный — за коробку.
    # Категория при этом не гарантирует триггер по строгому назначению (в ней
    # попадаются добавки/замазки/фотообои и т.п.) — поэтому берём цену из ЛЮБОГО
    # блока, чья витринная единица совпадает с ожидаемой, и отбрасываем позицию,
    # если ни один блок не подошёл (#277).
    accepted: frozenset[str]
    # Плинтус продаётся рейкой (витринная единица "шт."), а наша база — метр:
    # цену делим на длину рейки, извлечённую из названия товара ("...2.2 м").
    normalize_length: bool = False


MATERIAL_UNITS: dict[str, UnitSpec] = {
    "Краска для стен": UnitSpec(frozenset({"л"})),
    "Краска потолочная": UnitSpec(frozenset({"л"})),
    "Шпаклевка стартовая": UnitSpec(frozenset({"кг"})),
    "Шпаклевка финишная": UnitSpec(frozenset({"кг"})),
    "Грунтовка": UnitSpec(frozenset({"л"})),
    "Плиточный клей": UnitSpec(frozenset({"кг"})),
    "Затирка": UnitSpec(frozenset({"кг"})),
    "Плитка": UnitSpec(frozenset({"м²"})),
    "Ламинат": UnitSpec(frozenset({"м²"})),
    "Обои": UnitSpec(frozenset({"шт."})),  # 1 шт. = 1 рулон
    "Плинтус": UnitSpec(frozenset({"шт."}), normalize_length=True),
}

# Карта: материал в БД -> URL категории, сужённый фасетами (#319, #277). Общая
# категория kraski-dlya-sten-i-potolkov мешала стены и потолки (~2500 позиций,
# вилка 30→9672, ~320×) и обе строки указывали на один URL. Сужаем фасетами:
#   00277= — назначение: Стена / Потолок (аналог field142[] у Мегастроя);
#   14431= — тип шпаклёвки: Базовая / Финишная;
#   eligibilityByStores= — «в наличии» по казанским складам и двум ближайшим
#            пригородам (Солнечный, Залесный) — расширяет выборку без потери
#            региональности.
# Значения фасетов — кириллицей как в адресной строке; браузерный фетч (patchright)
# сам их perc-энкодит при переходе, отдельное кодирование не нужно. Семантический
# мусор (колеры/пробники/добавки/грунты) добиваем по имени ниже.
_PAINT_CATEGORY = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"
_SHPAKLEVKA_CATEGORY = "https://kazan.lemanapro.ru/catalogue/shpaklevki/"
_IN_STOCK_KAZAN = "eligibilityByStores=Казань_Казань Солнечный_Казань Залесный"

CATEGORY_MAP = {
    "Краска для стен": f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Стена",
    "Краска потолочная": f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Потолок",
    "Шпаклевка стартовая": f"{_SHPAKLEVKA_CATEGORY}?14431=Базовая шпатлёвка&{_IN_STOCK_KAZAN}",
    "Шпаклевка финишная": f"{_SHPAKLEVKA_CATEGORY}?14431=Финишная шпатлевка&{_IN_STOCK_KAZAN}",
    "Грунтовка": f"https://kazan.lemanapro.ru/search/?q=грунтовки&{_IN_STOCK_KAZAN}",
    "Плиточный клей": (
        f"https://kazan.lemanapro.ru/catalogue/klei-dlya-plitki-kamnya-i-izolyacii/"
        f"klei-dlya-plitki/?{_IN_STOCK_KAZAN}"
    ),
    "Затирка": f"https://kazan.lemanapro.ru/catalogue/zatirki-dlya-shvov-plitki/?{_IN_STOCK_KAZAN}",
    "Плитка": f"https://kazan.lemanapro.ru/catalogue/napolnaya-plitka/?{_IN_STOCK_KAZAN}",
    "Ламинат": f"https://kazan.lemanapro.ru/catalogue/laminat/?{_IN_STOCK_KAZAN}",
    "Обои": f"https://kazan.lemanapro.ru/catalogue/dekorativnye-oboi/?{_IN_STOCK_KAZAN}",
    "Плинтус": f"https://kazan.lemanapro.ru/catalogue/napolnye-plintusy/?{_IN_STOCK_KAZAN}",
}

# Обходим не всю выдачу: после ~15-й страницы у Лемана идут серые/нерелевантные
# позиции, они только искажают вилку и тянут прогон. С фасетным сужением (#319)
# осмысленных страниц ещё меньше — ранний стоп в leman_browser обычно срабатывает
# раньше этого потолка.
MAX_PAGES = 15

CARD_SELECTOR = '[data-qa="product"]'
_PRODUCT_ID_RE = re.compile(r"-(\d+)/?$")

# Витринная единица зашита в текст самого блока цены ("179 ₽/шт.", "50.4 ₽/кг")
# внутри вложенного [data-testid="price-unit"] — достаём токен после "₽/".
_UNIT_TEXT_RE = re.compile(r"₽\s*/\s*(\S+)")

# Плинтус продаётся рейкой ("...8 см 2.2 м") — длина всегда идёт последним числом
# перед отдельным "м" (не "см", не "мм" — те не граничат словом с "м").
_LENGTH_M_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м\b", re.UNICODE)

# Семантический мусор, который фасеты сайта не всегда отсекают: колеровочные
# пасты, пробники/образцы красок (по 30 ₽ — они и роняют min), грунтовки среди
# красок, добавки/красители среди затирок (issue-аналог #207).
_IRRELEVANT_NAME_MARKERS = ("колер", "пробник", "образец", "грунт", "тонир", "добавка", "краска для шв")


def _is_relevant(name: str | None) -> bool:
    if not name:
        # Имя не распарсилось — не выкидываем позицию (цена важнее), пусть решают
        # фасет URL и filter_outliers.
        return True
    low = name.lower()
    return not any(marker in low for marker in _IRRELEVANT_NAME_MARKERS)


def _build_page_url(base_url: str, page_num: int) -> str:
    # Пагинация Лемана 0-индексирована со 2-й страницы: 1-я страница — без
    # ?page, дальше ?page=1, ?page=2, ... Общая с leman_browser формула.
    if page_num == 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}page={page_num - 1}"


def _product_id(url: str | None) -> str | None:
    if not url:
        return None
    match = _PRODUCT_ID_RE.search(url)
    return match.group(1) if match else None


def _length_m_from_title(title: str | None) -> Decimal | None:
    if not title:
        return None
    match = _LENGTH_M_RE.search(title)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def _block_candidate(block) -> tuple[Decimal, str] | None:
    # Один ценовой блок карточки (основной или price-block-unitprice) -> пара
    # (цена, витринная единица), если у блока есть чистое числовое value и текст
    # единицы рядом. Блоки скидки/зачёркнутой цены сюда не передаются вызывающим
    # кодом (свои testid — price-block-oldprice/-discount).
    value = block.get("value")
    if not value:
        return None
    try:
        price = Decimal(value)
    except InvalidOperation:
        return None
    if price <= 0:
        return None
    unit_el = block.select_one('[data-testid="price-unit"]')
    if not unit_el:
        return None
    match = _UNIT_TEXT_RE.search(unit_el.get_text(strip=True))
    if not match:
        return None
    return price, match.group(1).strip()


def _parse_page(html: str, page_url: str) -> list[tuple[list[tuple[Decimal, str]], str | None, str | None]]:
    # Карточка товара в живой разметке каталога — [data-qa="product"]. Тройки
    # (кандидаты цены, ссылка, имя): кандидаты — все ценовые блоки карточки с
    # парой (цена, витринная единица), имя нужно для семантического отсева и
    # для нормализации плинтуса по длине из названия.
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(CARD_SELECTOR)
    results = []
    for item in items:
        candidates = []
        for block in item.select(
            '[data-testid="price-block-price"], [data-testid="price-block-unitprice"]'
        ):
            candidate = _block_candidate(block)
            if candidate:
                candidates.append(candidate)
        if not candidates:
            continue

        link_el = item.select_one('a[data-qa="product-name"][href]')
        href = link_el.get("href") if link_el else None
        url = urljoin(page_url, href.strip()) if href else None
        name = link_el.get_text(strip=True) if link_el else None

        results.append((candidates, url, name))
    return results


def _select_price(candidates: list[tuple[Decimal, str]], spec: UnitSpec) -> Decimal | None:
    for price, unit in candidates:
        if unit in spec.accepted:
            return price
    return None


class LemanParser(BaseParser):
    source_name = "Леман"

    def known_materials(self) -> list[str]:
        return list(CATEGORY_MAP.keys())

    def fetch_price(self, material_name: str) -> ParsedPrice:
        if material_name not in CATEGORY_MAP:
            raise ValueError(f"Нет категории Лемана для материала '{material_name}'")

        if not settings.LEMAN_LIVE:
            # Cookie-харвест + requests (как у Мегастроя) для Лемана не работает —
            # Qrator ловит CDP-утечки даже у headed настоящего Chrome без patchright
            # (см. app/parsers/leman_browser.py). Без явного включения браузерного
            # фетча в сеть не ходим вовсе — сразу уходим в seed-fallback, не тратя
            # время на заведомо безуспешный запрос.
            raise RuntimeError(
                f"LEMAN_LIVE выключен — живой фетч Лемана для '{material_name}' пропущен"
            )

        spec = MATERIAL_UNITS[material_name]
        base_url = CATEGORY_MAP[material_name]
        pages_html = leman_browser.fetch_pages(base_url, MAX_PAGES)
        if not pages_html:
            raise RuntimeError(f"Леман: браузерный фетч не вернул ни одной страницы для '{material_name}'")

        items: list[tuple[Decimal, str | None, str | None]] = []
        seen_ids: set[str] = set()
        for page_num, html in enumerate(pages_html, start=1):
            page_url = _build_page_url(base_url, page_num)
            page_items = _parse_page(html, page_url)
            new_items = []
            for candidates, url, name in page_items:
                product_id = _product_id(url)
                if product_id is not None:
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                price = _select_price(candidates, spec)
                if price is None:
                    # Ни основной, ни вторичный блок не дали нужную единицу
                    # (напр. клей без price-block-unitprice) — не считаем товар.
                    continue

                if spec.normalize_length:
                    length_m = _length_m_from_title(name)
                    if not length_m:
                        continue
                    price = price / length_m

                new_items.append((price, url, name))

            items.extend(new_items)
            logger.info(f"  Леман '{material_name}' стр.{page_num}: +{len(new_items)} цен")

        if not items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (единица/размер не распознаны)")

        # Семантический отсев по имени (колеры/пробники/добавки/грунты) до статистики —
        # именно пробники по 30 ₽ роняли min и перекашивали вилку. Если фильтр
        # вдруг выкосил всё (имена не распарсились/разметка сменилась), откатываемся
        # к исходной выборке — цена не должна пропасть и уйти в seed.
        relevant = [it for it in items if _is_relevant(it[2])]
        if relevant and len(relevant) < len(items):
            logger.info(
                f"  Леман '{material_name}': отброшено нерелевантных подтипов "
                f"{len(items) - len(relevant)} из {len(items)}"
            )
            items = relevant

        raw_count = len(items)
        items = filter_outliers(items, key=lambda it: it[0])
        if len(items) < raw_count:
            logger.info(
                f"  Леман '{material_name}': отброшено выбросов "
                f"{raw_count - len(items)} из {raw_count}"
            )

        all_prices = [price for price, _, _ in items]
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
