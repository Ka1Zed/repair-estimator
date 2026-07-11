import json
import logging
import os
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"

# Кэш clearance-cookie DDoS-Guard на диске: харвестим headless-браузером редко
# (по результатам ручного прогона ключевые DDoS-Guard куки живут ~53ч, не
# минуты), а не на каждый запрос update_prices.
CACHE_PATH = CACHE_DIR / "megastroy_cookie.json"

# Запас сильно меньше эмпирически замеренного TTL (~53ч у __ddg8_/9_/10_),
# чтобы не словить протухший cookie на старте долгого прогона update_prices.
COOKIE_TTL_SECONDS = 3 * 60 * 60  # 3 часа

# Куки, которые реально нужны DDoS-Guard + сайту, чтобы отдать страницу (без
# аналитического мусора вроде session_timer_*/dSesn/_dvs/seconds_on_page_*,
# который не влияет на прохождение challenge — проверено прогоном).
_KEEP_PREFIXES = (
    "__ddg",
    "PHPSESSID",
    "detected_city_id",
    "is_common_market",
    "confirmed_domain",
    "is_city_confirmed",
    "city_id",
)


def _read_cache(cache_path: Path) -> str | None:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - data.get("harvested_at", 0) > COOKIE_TTL_SECONDS:
        return None
    return data.get("cookie") or None


def _write_cache(cache_path: Path, cookie: str) -> None:
    # Пишем через temp-файл с уникальным суффиксом (pid) + rename: rename атомарен
    # на одной ФС, поэтому параллельный update_prices не увидит "разорванный"
    # частично записанный JSON. Права 0600 — cookie не должна быть читаема всем.
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps({"cookie": cookie, "harvested_at": time.time()}))
    tmp_path.chmod(0o600)
    tmp_path.replace(cache_path)


def _collect_cookies(
    url: str,
    user_agent: str,
    *,
    site_label: str,
    ready_check: Callable[[object], bool] | None = None,
) -> dict[str, str] | None:
    # Общая механика для всех сайтов: запустить headless Chromium, открыть
    # страницу, дождаться готовности (по умолчанию — networkidle; сайты с
    # JS-challenge вроде Мегастроя передают свою проверку через ready_check) и
    # забрать куки контекста. Ошибка/отсутствие patchright — не исключение, а
    # None, чтобы вызывающий код спокойно ушёл в обычный путь без cookie.
    # patchright (не playwright) — drop-in замена с патчами против CDP-детекта;
    # используем везде, включая Мегастрой, чтобы не тащить оба пакета разом
    # (конфликт версии pyee — pip check ругался при обоих одновременно).
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            f"{site_label}: headless включён, но patchright не установлен "
            "(pip install -r requirements-headless.txt && patchright install chrome)"
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=user_agent, locale="ru-RU")
                page = context.new_page()
                if ready_check is not None:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    for _ in range(20):
                        if ready_check(page):
                            break
                        time.sleep(1)
                    else:
                        logger.warning(f"{site_label}: headless не прошёл проверку готовности за 20с")
                        return None
                else:
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                return {c["name"]: c["value"] for c in context.cookies()}
            finally:
                browser.close()
    except Exception:
        logger.exception(f"{site_label}: ошибка headless-харвестера cookie")
        return None


def _harvest(url: str, user_agent: str) -> str | None:
    # DDoS-Guard сам перезагружает страницу после прохождения JS-challenge —
    # готовность определяем по смене title. Регистр title не гарантирован
    # (видели и "DDoS-Guard", и "DDOS-GUARD" — интерактивная капча) — сравниваем
    # без учёта регистра, иначе ready_check ложно считает капчу пройденной и
    # харвест кэширует нерабочий cookie как успешный.
    cookies = _collect_cookies(
        url, user_agent,
        site_label="Мегастрой",
        ready_check=lambda page: page.title().strip().lower() != "ddos-guard",
    )
    if not cookies:
        return None

    minimal = {k: v for k, v in cookies.items() if k.startswith(_KEEP_PREFIXES)}
    if not minimal:
        return None
    return "; ".join(f"{k}={v}" for k, v in minimal.items())


def get_megastroy_cookie(url: str, user_agent: str) -> str | None:
    """Clearance-cookie DDoS-Guard для Мегастроя: из кэша, иначе headless-харвест.

    Никогда не бросает исключения — сбой headless значит просто None
    (вызывающий код уходит в обычный путь без cookie -> 403 -> seed-fallback).
    """
    cached = _read_cache(CACHE_PATH)
    if cached:
        return cached

    cookie = _harvest(url, user_agent)
    if cookie:
        _write_cache(CACHE_PATH, cookie)
    return cookie
