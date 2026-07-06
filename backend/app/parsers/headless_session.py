import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Кэш clearance-cookie DDoS-Guard на диске: харвестим headless-браузером редко
# (см. результаты прогона в plans/2026-06-30-beta-headless-parser.md — ключевые
# DDoS-Guard куки живут ~53ч, не минуты), а не на каждый запрос update_prices.
CACHE_PATH = Path(__file__).resolve().parent.parent.parent / ".cache" / "megastroy_cookie.json"

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


def _read_cache() -> str | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - data.get("harvested_at", 0) > COOKIE_TTL_SECONDS:
        return None
    return data.get("cookie") or None


def _write_cache(cookie: str) -> None:
    # Пишем через temp-файл с уникальным суффиксом (pid) + rename: rename атомарен
    # на одной ФС, поэтому параллельный update_prices не увидит "разорванный"
    # частично записанный JSON. Права 0600 — cookie не должна быть читаема всем.
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_PATH.with_name(f"{CACHE_PATH.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps({"cookie": cookie, "harvested_at": time.time()}))
    tmp_path.chmod(0o600)
    tmp_path.replace(CACHE_PATH)


def _harvest(url: str, user_agent: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "MEGASTROY_HEADLESS=1, но playwright не установлен "
            "(pip install -r requirements-headless.txt && playwright install chromium)"
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=user_agent, locale="ru-RU")
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                # DDoS-Guard сам перезагружает страницу после прохождения JS-challenge.
                for _ in range(20):
                    if page.title() != "DDoS-Guard":
                        break
                    time.sleep(1)
                else:
                    logger.warning("Мегастрой: headless не прошёл JS-challenge за 20с")
                    return None
                cookies = {c["name"]: c["value"] for c in context.cookies()}
            finally:
                browser.close()
    except Exception:
        logger.exception("Мегастрой: ошибка headless-харвестера cookie")
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
    cached = _read_cache()
    if cached:
        return cached

    cookie = _harvest(url, user_agent)
    if cookie:
        _write_cache(cookie)
    return cookie
