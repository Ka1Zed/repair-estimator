import logging
import time

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


def fetch_pages(base_url: str, max_pages: int) -> list[str]:
    """Постранично открывает каталог Лемана в patchright-браузере и возвращает HTML
    каждой страницы (для последующего разбора _parse_page в leman_parser).

    Никогда не бросает исключения наружу — сбой patchright/сети/челленджа значит
    просто пустой или неполный список; вызывающий код (leman_parser.fetch_price)
    сам решает, достаточно ли собранных страниц, и уходит в seed-fallback, если
    страниц нет вовсе.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "Леман: LEMAN_LIVE включён, но patchright не установлен "
            "(pip install -r requirements-headless.txt && patchright install chrome)"
        )
        return []

    pages_html: list[str] = []
    sep = "&" if "?" in base_url else "?"

    try:
        with sync_playwright() as p:
            # headless=False + channel="chrome" обязательны: headless и/или
            # ванильный Chromium Qrator режет ещё на JS-challenge.
            browser = p.chromium.launch(headless=False, channel="chrome")
            try:
                context = browser.new_context(locale="ru-RU")
                page = context.new_page()

                for page_num in range(1, max_pages + 1):
                    # Пагинация Лемана 0-индексирована со 2-й страницы сайта:
                    # 1-я страница — без ?page, дальше ?page=1, ?page=2, ...
                    url = base_url if page_num == 1 else f"{base_url}{sep}page={page_num - 1}"

                    try:
                        page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
                        page.wait_for_selector(CARD_SELECTOR, timeout=NAV_TIMEOUT_MS)
                    except Exception:
                        logger.info(f"  Леман браузер стр.{page_num}: карточки не дождались, стоп")
                        break

                    # Небольшой скролл + networkidle — часть карточек на каталоге
                    # Лемана дорисовывается лениво при скролле/гидратации.
                    page.mouse.wheel(0, 4000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
                    except Exception:
                        pass

                    pages_html.append(page.content())
                    time.sleep(PAGE_PAUSE_SECONDS)
            finally:
                browser.close()
    except Exception:
        logger.exception("Леман: ошибка браузерного фетча каталога")

    return pages_html
