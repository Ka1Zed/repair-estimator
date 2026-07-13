import logging
import re
import time

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# lemanapro.ru стоит за Qrator с JS proof-of-work: голый requests и обычный
# playwright (даже headed настоящий Chrome) получают 401/"Server error" — Qrator
# палит CDP-утечки (Runtime.enable). Рабочий рецепт, подтверждённый ручными
# прогонами: patchright (пропатченный playwright) + channel="chrome" + headed +
# РФ-IP. Поэтому здесь — не cookie-харвест с последующим requests, а фетч HTML
# целиком внутри браузерной сессии.
CARD_SELECTOR = '[data-qa="product"]'
NAV_TIMEOUT_MS = 30_000
PAGE_PAUSE_SECONDS = 1.0  # вежливая пауза между страницами, не долбить сайт
# Каталог за Qrator тянет аналитику/qauth постоянными коннектами — networkidle
# на нём почти никогда не наступает и раньше съедал полный NAV_TIMEOUT (~30с) на
# КАЖДОЙ странице (×MAX_PAGES = десятки минут). Карточки уже дождались по
# CARD_SELECTOR, скролл нужен лишь чтобы дорисовать «хвост» ленивых карточек —
# для этого хватает короткой фиксированной паузы, а не ожидания тишины сети.
LAZY_SETTLE_MS = 1_500

_PRODUCT_ID_RE = re.compile(r"-(\d+)/?$")


def _page_signature(html: str) -> frozenset[str]:
    # Набор id товаров на странице — по хвосту ссылки карточки. Нужен, чтобы
    # поймать overflow: за последней реальной страницей Леман переклинивает ?page
    # на ту же выдачу, и мы бы вхолостую догоняли до MAX_PAGES один и тот же список.
    soup = BeautifulSoup(html, "html.parser")
    ids = set()
    for link in soup.select(f'{CARD_SELECTOR} a[data-qa="product-name"][href]'):
        match = _PRODUCT_ID_RE.search(link.get("href", ""))
        if match:
            ids.add(match.group(1))
    return frozenset(ids)


def _fetch_pages_with_context(context, base_url: str, max_pages: int) -> list[str]:
    """Постранично открывает каталог в НОВОЙ ВКЛАДКЕ уже готового браузерного
    контекста (прошедшего Qrator-challenge при запуске сессии) и возвращает HTML
    каждой страницы (для последующего разбора _parse_page в leman_parser).

    Не бросает исключения наружу — сбой сети/челленджа значит просто пустой
    или неполный список; вызывающий код (LemanParser.fetch_price) сам решает,
    достаточно ли собранных страниц, и уходит в seed-fallback, если страниц нет.
    """
    pages_html: list[str] = []
    sep = "&" if "?" in base_url else "?"

    page = context.new_page()
    try:
        prev_signature: frozenset[str] = frozenset()
        for page_num in range(1, max_pages + 1):
            # Пагинация Лемана 0-индексирована со 2-й страницы сайта:
            # 1-я страница — без ?page, дальше ?page=1, ?page=2, ...
            url = base_url if page_num == 1 else f"{base_url}{sep}page={page_num - 1}"

            # Весь per-page блок под общим try: краш/закрытие вкладки
            # (TargetClosedError) в любой момент — на goto, скролле или
            # .content() — значит просто стоп; уже собранные в pages_html
            # страницы не теряем (см. контракт в докстринге).
            try:
                page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
                page.wait_for_selector(CARD_SELECTOR, timeout=NAV_TIMEOUT_MS)
                # Небольшой скролл дорисовывает лениво-подгружаемые карточки;
                # даём им короткую фиксированную паузу вместо networkidle (см.
                # LAZY_SETTLE_MS — networkidle на Qrator-SPA не наступает).
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(LAZY_SETTLE_MS)
                html = page.content()
            except Exception:
                logger.info(f"  Леман браузер стр.{page_num}: страница не отдалась, стоп")
                break

            # Overflow-защита: та же выдача, что и на прошлой странице —
            # дальше идти бессмысленно, каталог кончился.
            signature = _page_signature(html)
            if signature and signature == prev_signature:
                logger.info(f"  Леман браузер стр.{page_num}: повтор предыдущей, стоп")
                break
            prev_signature = signature

            pages_html.append(html)
            time.sleep(PAGE_PAUSE_SECONDS)
    finally:
        try:
            page.close()
        except Exception:
            # Вкладка уже могла рухнуть (TargetClosedError) — это не должно
            # затирать уже собранные страницы.
            logger.debug("Леман: вкладка уже закрыта/недоступна при close()")

    return pages_html


class LemanBrowserSession:
    """Держит один браузер и контекст открытыми между несколькими fetch_pages —
    без этого на КАЖДУЮ категорию (материалов 11+, у затирки вдобавок 4
    подкатегории, #277) заново поднимался бы целый процесс Chrome, хотя после
    первого прохождения Qrator-challenge достаточно открыть новую вкладку в той
    же сессии. Используется в app/manage.py update_prices — открывается один
    раз на весь прогон материалов Лемана, закрывается после последнего.

    Вне общей сессии (тесты, единичный вызов) остаётся модульная fetch_pages() —
    сама открывает и сразу закрывает такую сессию на один вызов.
    """

    def __init__(self):
        self._playwright_cm = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "LemanBrowserSession":
        try:
            from patchright.sync_api import sync_playwright
        except ImportError:
            logger.warning(
                "Леман: LEMAN_LIVE включён, но patchright не установлен "
                "(pip install -r requirements-headless.txt && patchright install chrome)"
            )
            return self

        self._playwright_cm = sync_playwright()
        try:
            playwright = self._playwright_cm.__enter__()
            # headless=False + channel="chrome" обязательны: headless и/или
            # ванильный Chromium Qrator режет ещё на JS-challenge.
            self._browser = playwright.chromium.launch(headless=False, channel="chrome")
            self._context = self._browser.new_context(locale="ru-RU")
        except Exception:
            logger.exception("Леман: не удалось поднять браузер для сессии")
            try:
                self._playwright_cm.__exit__(None, None, None)
            except Exception:
                logger.debug("Леман: playwright уже недоступен при откате сессии")
            self._playwright_cm = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                logger.debug("Леман: браузер уже закрыт/недоступен при close()")
        if self._playwright_cm is not None:
            self._playwright_cm.__exit__(exc_type, exc, tb)

    def fetch_pages(self, base_url: str, max_pages: int) -> list[str]:
        if self._context is None:
            # patchright не установлен или браузер не поднялся при __enter__ —
            # тот же контракт "никогда не бросает исключения", что и раньше.
            return []
        try:
            return _fetch_pages_with_context(self._context, base_url, max_pages)
        except Exception:
            logger.exception("Леман: ошибка браузерного фетча каталога")
            return []


def fetch_pages(base_url: str, max_pages: int) -> list[str]:
    """Совместимость для единичных вызовов вне общей сессии (тесты, разовый
    фетч без update_prices) — открывает свою LemanBrowserSession и сразу
    закрывает её после одной категории."""
    with LemanBrowserSession() as session:
        return session.fetch_pages(base_url, max_pages)
