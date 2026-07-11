import logging
import re
import statistics
import time
from contextlib import nullcontext
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.core.config import settings
from app.parsers import leman_browser
from app.parsers._stats import filter_outliers, price_band_slice
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
    # Вариант по уровню комплектации (#331): "low"/"high" — нижняя/верхняя
    # треть цен категории (price_band_slice), None — вся категория (стандарт).
    # Как и у Мегастроя — приближение через терции, а не курированный facet
    # по бренду (сайт даёт такой facet только у краски, стена/потолок).
    price_band: str | None = None


MATERIAL_UNITS: dict[str, UnitSpec] = {
    "Краска для стен": UnitSpec(frozenset({"л"})),
    "Краска для стен эконом": UnitSpec(frozenset({"л"}), price_band="low"),
    "Краска для стен премиум": UnitSpec(frozenset({"л"}), price_band="high"),
    "Краска потолочная": UnitSpec(frozenset({"л"})),
    "Краска потолочная премиум": UnitSpec(frozenset({"л"}), price_band="high"),
    "Шпаклевка стартовая": UnitSpec(frozenset({"кг"})),
    "Шпаклевка финишная": UnitSpec(frozenset({"кг"})),
    "Грунтовка": UnitSpec(frozenset({"л"})),
    "Плиточный клей": UnitSpec(frozenset({"кг"})),
    "Затирка": UnitSpec(frozenset({"кг"})),
    "Плитка": UnitSpec(frozenset({"м²"})),
    "Плитка эконом": UnitSpec(frozenset({"м²"}), price_band="low"),
    "Плитка премиум": UnitSpec(frozenset({"м²"}), price_band="high"),
    "Ламинат": UnitSpec(frozenset({"м²"})),
    "Ламинат эконом": UnitSpec(frozenset({"м²"}), price_band="low"),
    "Ламинат премиум": UnitSpec(frozenset({"м²"}), price_band="high"),
    "Обои": UnitSpec(frozenset({"шт."})),  # 1 шт. = 1 рулон
    "Обои эконом": UnitSpec(frozenset({"шт."}), price_band="low"),
    "Обои премиум": UnitSpec(frozenset({"шт."}), price_band="high"),
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

CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "Краска для стен": (f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Стена",),
    # Варианты по уровню (#331) — тот же URL категории, price_band (MATERIAL_UNITS)
    # режет уже найденные товары на терции вместо ещё одного facet-сужения.
    "Краска для стен эконом": (f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Стена",),
    "Краска для стен премиум": (f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Стена",),
    "Краска потолочная": (f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Потолок",),
    "Краска потолочная премиум": (f"{_PAINT_CATEGORY}?{_IN_STOCK_KAZAN}&00277=Потолок",),
    "Шпаклевка стартовая": (f"{_SHPAKLEVKA_CATEGORY}?14431=Базовая шпатлёвка&{_IN_STOCK_KAZAN}",),
    "Шпаклевка финишная": (f"{_SHPAKLEVKA_CATEGORY}?14431=Финишная шпатлевка&{_IN_STOCK_KAZAN}",),
    "Грунтовка": (f"https://kazan.lemanapro.ru/search/?q=грунтовки&{_IN_STOCK_KAZAN}",),
    "Плиточный клей": (
        f"https://kazan.lemanapro.ru/catalogue/klei-dlya-plitki-kamnya-i-izolyacii/"
        f"klei-dlya-plitki/?{_IN_STOCK_KAZAN}",
    ),
    # zatirki-dlya-shvov-plitki/ — хаб-страница с плитками подкатегорий, без
    # карточек товаров; берём реальные листинги по типам затирки напрямую.
    # Полиуретановая недоступна в Казани (только онлайн-заказ) — не берём.
    "Затирка": (
        f"https://kazan.lemanapro.ru/catalogue/zatirki-cementnye-dlya-plitki/?{_IN_STOCK_KAZAN}",
        f"https://kazan.lemanapro.ru/catalogue/zatirki-epoksidnye-dlya-plitki/?{_IN_STOCK_KAZAN}",
        f"https://kazan.lemanapro.ru/catalogue/zatirki-polimernye-dlya-plitki/?{_IN_STOCK_KAZAN}",
        f"https://kazan.lemanapro.ru/catalogue/zatirki-silikonovye-dlya-plitki/?{_IN_STOCK_KAZAN}",
    ),
    "Плитка": (f"https://kazan.lemanapro.ru/catalogue/napolnaya-plitka/?{_IN_STOCK_KAZAN}",),
    "Плитка эконом": (f"https://kazan.lemanapro.ru/catalogue/napolnaya-plitka/?{_IN_STOCK_KAZAN}",),
    "Плитка премиум": (f"https://kazan.lemanapro.ru/catalogue/napolnaya-plitka/?{_IN_STOCK_KAZAN}",),
    "Ламинат": (f"https://kazan.lemanapro.ru/catalogue/laminat/?{_IN_STOCK_KAZAN}",),
    "Ламинат эконом": (f"https://kazan.lemanapro.ru/catalogue/laminat/?{_IN_STOCK_KAZAN}",),
    "Ламинат премиум": (f"https://kazan.lemanapro.ru/catalogue/laminat/?{_IN_STOCK_KAZAN}",),
    "Обои": (f"https://kazan.lemanapro.ru/catalogue/dekorativnye-oboi/?{_IN_STOCK_KAZAN}",),
    "Обои эконом": (f"https://kazan.lemanapro.ru/catalogue/dekorativnye-oboi/?{_IN_STOCK_KAZAN}",),
    "Обои премиум": (f"https://kazan.lemanapro.ru/catalogue/dekorativnye-oboi/?{_IN_STOCK_KAZAN}",),
    "Плинтус": (f"https://kazan.lemanapro.ru/catalogue/napolnye-plintusy/?{_IN_STOCK_KAZAN}",),
}

# Обходим не всю выдачу: после ~15-й страницы у Лемана идут серые/нерелевантные
# позиции, они только искажают вилку и тянут прогон. С фасетным сужением (#319)
# осмысленных страниц ещё меньше — ранний стоп в leman_browser обычно срабатывает
# раньше этого потолка.
MAX_PAGES = 15

# Вариантные материалы (эконом/премиум, #331) указывают на тот же base_urls, что
# и стандарт — кэш карточек категории по base_urls (#341), чтобы update_prices не
# гонял браузер за одной и той же выдачей 2-3 раза подряд для трёх вариантов.
# TTL небольшой — нужен только на время обработки одной группы вариантов в
# рамках одного прогона (см. megastroy_parser._CATEGORY_CACHE_TTL_SECONDS).
_CATEGORY_CACHE_TTL_SECONDS = 600

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
    # value может прийти с форматированием (пробелы/nbsp как разделитель тысяч,
    # запятая-десятичная) — нормализуем перед Decimal, иначе валидная цена
    # молча отсеется и вся выборка может схлопнуться в "не найдено цен".
    normalized = value.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        price = Decimal(normalized)
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


def _select_package_size(
    candidates: list[tuple[Decimal, str]], spec: UnitSpec, base_price: Decimal
) -> Decimal | None:
    # Карточка Лемана держит до двух ценовых блоков: тот, что совпал с
    # ожидаемой единицей (base_price — уже выбран в _select_price выше), и,
    # если карточка его показывает, второй — цена за упаковку/коробку целиком
    # ("2 232 ₽/шт.", "1 295 ₽/кор."). У краски/шпаклёвки/грунтовки/клея это
    # ВТОРОЙ блок относительно unitprice, у плитки/ламината — наоборот
    # (unitprice там и есть цена за коробку, см. #319 в docs/price-sources.md),
    # но формула не зависит от того, какой блок какой: package_size = цена
    # упаковки / цена базовой единицы. Берём первый кандидат с ДРУГОЙ единицей —
    # у Лемана на карточке их максимум два, так что это однозначно "второй" блок.
    if base_price <= 0:
        return None
    for price, unit in candidates:
        if unit not in spec.accepted:
            return price / base_price
    return None


class LemanParser(BaseParser):
    source_name = "Леман"

    def __init__(self):
        # Опциональная общая браузерная сессия (см. leman_browser.LemanBrowserSession) —
        # update_prices() открывает её один раз на весь прогон материалов Лемана
        # и подставляет через set_session, чтобы не поднимать Chrome заново на
        # каждую категорию (материалов 11+, у затирки ещё и 4 подкатегории, #277).
        # None — прежнее поведение: каждый fetch_price сам открывает и закрывает
        # свою сессию через модульную leman_browser.fetch_pages.
        self._session = None
        # Кэш карточек категории по base_urls (#341) — см. _CATEGORY_CACHE_TTL_SECONDS.
        self._raw_cache: dict[tuple[str, ...], tuple[float, list]] = {}

    def set_session(self, session) -> None:
        self._session = session

    def open_session(self):
        # Раз даже с общей сессией фетч идёт через реальный браузер, нет смысла
        # поднимать Chrome, если живой фетч всё равно выключен — fetch_price
        # ниже сразу упадёт в RuntimeError на каждом материале.
        if not settings.LEMAN_LIVE:
            return nullcontext(None)
        return leman_browser.LemanBrowserSession()

    def known_materials(self) -> list[str]:
        return list(CATEGORY_MAP.keys())

    def _fetch_raw_candidates(
        self, base_urls: tuple[str, ...], material_name: str
    ) -> list[tuple[list[tuple[Decimal, str]], str | None, str | None]]:
        # Тройки (кандидаты цены, ссылка, имя) со всех страниц категории, уже
        # дедуплицированные по id товара — разбор, не зависящий от spec конкретного
        # варианта (тот применяется выше по стеку в fetch_price). Вариантные
        # материалы (эконом/премиум) шлют тот же base_urls — при повторном вызове
        # в пределах TTL отдаём уже скачанное, не поднимая браузер заново.
        cached = self._raw_cache.get(base_urls)
        if cached is not None:
            fetched_at, raw = cached
            if time.monotonic() - fetched_at < _CATEGORY_CACHE_TTL_SECONDS:
                logger.info(
                    f"  Леман '{material_name}': категория {base_urls[0]} из кэша "
                    f"({len(raw)} карточек, без повторного фетча)"
                )
                return raw

        fetch_pages = self._session.fetch_pages if self._session is not None else leman_browser.fetch_pages

        raw: list[tuple[list[tuple[Decimal, str]], str | None, str | None]] = []
        seen_ids: set[str] = set()
        any_pages_loaded = False

        for base_url in base_urls:
            pages_html = fetch_pages(base_url, MAX_PAGES)
            if not pages_html:
                logger.warning(f"  Леман '{material_name}' {base_url}: браузер не вернул ни одной страницы")
                continue
            any_pages_loaded = True

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
                    new_items.append((candidates, url, name))

                raw.extend(new_items)
                logger.info(f"  Леман '{material_name}' {base_url} стр.{page_num}: +{len(new_items)} карточек")

        if not any_pages_loaded:
            raise RuntimeError(f"Леман: браузерный фетч не вернул ни одной страницы для '{material_name}'")

        self._raw_cache[base_urls] = (time.monotonic(), raw)
        return raw

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
        base_urls = CATEGORY_MAP[material_name]
        raw = self._fetch_raw_candidates(base_urls, material_name)

        items: list[tuple[Decimal, str | None, str | None, Decimal | None]] = []
        for candidates, url, name in raw:
            price = _select_price(candidates, spec)
            if price is None:
                # Ни основной, ни вторичный блок не дали нужную единицу
                # (напр. клей без price-block-unitprice) — не считаем товар.
                continue

            if spec.normalize_length:
                length_m = _length_m_from_title(name)
                if not length_m:
                    continue
                # Длина рейки — она же и есть package_size (м на упаковку).
                package_size = length_m
                price = price / length_m
            else:
                # package_size (#306) — фасовка ЭТОГО товара, если карточка
                # показывает второй ценовой блок (см. _select_package_size).
                package_size = _select_package_size(candidates, spec, price)

            items.append((price, url, name, package_size))

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

        # Вариант по уровню комплектации (#331): нижняя/верхняя треть цен категории
        # вместо всей выборки — см. price_band_slice и docs/price-sources.md.
        if spec.price_band:
            band_count = len(items)
            items = price_band_slice(items, spec.price_band, key=lambda it: it[0])
            logger.info(
                f"  Леман '{material_name}': price_band={spec.price_band}, "
                f"{len(items)} из {band_count} цен"
            )

        all_prices = [price for price, _, _, _ in items]
        price_min = min(all_prices)
        price_max = max(all_prices)
        price_avg = Decimal(round(statistics.mean(all_prices)))

        # package_size берём у ТОГО ЖЕ товара-представителя (#306) — иначе
        # фасовка в смете и фасовка на странице source_url могут не совпадать.
        representative = min(items, key=lambda it: abs(it[0] - price_avg))
        source_url = representative[1] or base_urls[0]
        package_size = representative[3]

        logger.info(
            f"Леман: '{material_name}' — всего {len(all_prices)} цен, "
            f"min={price_min}, avg={price_avg}, max={price_max}, source={source_url}"
        )

        return ParsedPrice(
            price_min=price_min,
            price_avg=price_avg,
            price_max=price_max,
            source_url=source_url,
            package_size=package_size,
        )
