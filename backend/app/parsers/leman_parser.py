import logging
import re
import statistics
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import leman_browser
from app.parsers._stats import filter_outliers
from app.parsers.base import BaseParser, ParsedPrice

logger = logging.getLogger(__name__)

# Карта: материал в БД -> URL категории, сужённый фасетами (#319). Общая категория
# kraski-dlya-sten-i-potolkov мешала стены и потолки (~2500 позиций, вилка 30→9672,
# ~320×) и обе строки указывали на один URL. Сужаем двумя фасетами:
#   00277= — назначение: Стена / Потолок (разводит выборки, аналог field142[] у
#            Мегастроя);
#   eligibilityByStores=Казань + fromRegion=34 — «в наличии» по казанским складам
#            (~108 из ~2500): убирает серые/нет-в-наличии позиции и режет прогон.
# Значения фасетов — кириллицей как в адресной строке; браузерный фетч (patchright)
# сам их perc-энкодит при переходе, отдельное кодирование не нужно. Семантический
# мусор (колеры/пробники/грунты) добиваем по имени ниже.
_PAINT_CATEGORY = "https://kazan.lemanapro.ru/catalogue/kraski-dlya-sten-i-potolkov/"
_IN_STOCK_KAZAN = "fromRegion=34&eligibilityByStores=Казань"
CATEGORY_MAP = {
    "Краска для стен": f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Стена",
    "Краска потолочная": f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Потолок",
}

# Обходим не всю выдачу: после ~15-й страницы у Лемана идут серые/нерелевантные
# позиции, они только искажают вилку и тянут прогон. С фасетным сужением (#319)
# осмысленных страниц ещё меньше — ранний стоп в leman_browser обычно срабатывает
# раньше этого потолка.
MAX_PAGES = 15

CARD_SELECTOR = '[data-qa="product"]'
_PRODUCT_ID_RE = re.compile(r"-(\d+)/?$")

# Семантический мусор в категории красок, который фасеты сайта не всегда отсекают:
# колеровочные пасты, пробники/образцы (по 30 ₽ — они и роняют min), грунтовки.
# Страховка к фасетному сужению URL (issue-аналог #207): даже с фильтром «тип/
# назначение» в выдачу просачиваются сопутствующие подтипы. Сверяем по имени
# товара из карточки, в нижнем регистре.
_IRRELEVANT_NAME_MARKERS = ("колер", "пробник", "образец", "грунт", "тонир")


def _is_relevant_paint(name: str | None) -> bool:
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


def _parse_page(html: str, page_url: str) -> list[tuple[Decimal, str | None, str | None]]:
    # Карточка товара в живой разметке каталога — [data-qa="product"] (без
    # моб./десктоп дублей, в отличие от старой SSR-разметки). Дедуп между
    # страницами — на стороне fetch_price (по id товара из хвоста ссылки).
    # Тройки (цена, ссылка, имя): имя нужно, чтобы отсеять семантический мусор
    # (колеры/пробники/грунты) в fetch_price.
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(CARD_SELECTOR)
    results = []
    for item in items:
        price_el = item.select_one('[data-testid="price-block-price"]')
        if not price_el:
            continue
        value = price_el.get("value")
        if not value:
            continue
        # value может прийти с форматированием (пробелы/nbsp как разделитель тысяч,
        # запятая-десятичная) — нормализуем перед Decimal, иначе валидная цена
        # молча отсеется и вся выборка может схлопнуться в "не найдено цен".
        normalized = value.replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            price = Decimal(normalized)
        except (InvalidOperation, ValueError):
            continue
        if price <= 0:
            continue

        link_el = item.select_one('a[data-qa="product-name"][href]')
        href = link_el.get("href") if link_el else None
        url = urljoin(page_url, href.strip()) if href else None
        name = link_el.get_text(strip=True) if link_el else None

        results.append((price, url, name))
    return results


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
            for price, url, name in page_items:
                product_id = _product_id(url)
                if product_id is not None:
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)
                new_items.append((price, url, name))

            items.extend(new_items)
            logger.info(f"  Леман '{material_name}' стр.{page_num}: +{len(new_items)} цен")

        if not items:
            raise RuntimeError(f"Не найдено цен для '{material_name}' (возможно, урезанная страница)")

        # Семантический отсев по имени (колеры/пробники/грунты) до статистики —
        # именно пробники по 30 ₽ роняли min и перекашивали вилку. Если фильтр
        # вдруг выкосил всё (имена не распарсились/разметка сменилась), откатываемся
        # к исходной выборке — цена не должна пропасть и уйти в seed.
        relevant = [it for it in items if _is_relevant_paint(it[2])]
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
