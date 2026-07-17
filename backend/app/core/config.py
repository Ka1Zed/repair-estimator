from pydantic import SecretStr  
from pydantic_settings import BaseSettings, SettingsConfigDict  
from pathlib import Path
ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"

class DBSettings(BaseSettings):
    POSTGRES_USER: str = "repair"
    POSTGRES_PASSWORD: SecretStr = "repair"
    POSTGRES_DB: str = "repair_estimator"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Сколько часов считать спарсенную цену актуальной, прежде чем дёргать парсер снова.
    # Запрос сметы не ходит в интернет, если в БД есть свежая цена парсера.
    PRICE_TTL_HOURS: int = 24

    # Потолок давности для устаревшей (>PRICE_TTL_HOURS) цены парсера: если живой
    # рефетч не удался (403/VPN/парсер выключен), но старая цена парсера моложе
    # PRICE_STALE_TTL_HOURS — отдаём её вместо общей seed-цены. Seed — не
    # консервативный эталон, а генерируемый снимок, который сам заметно расходится
    # с рыночными ценами (см. docs/price-sources.md), поэтому цена парсера месячной
    # давности всё ещё точнее seed. Обновление прода ручное (нет cron, см.
    # docs/price-refresh.md) — реальный интервал обновления непредсказуем и легко
    # превышает неделю, отсюда месяц, а не неделя. Не ∞: без потолка баг парсера
    # (мисселект товара-представителя и т.п.) или тихая поломка update_prices жили
    # бы в кэше бесконечно без какого-либо мониторинга возраста цены. Старше месяца
    # — считаем, что парсер сломан надолго, и уходим в seed.
    PRICE_STALE_TTL_HOURS: int = 24 * 30

    # Ходить ли в живой парсер материалов при расчёте сметы. На сервере в
    # дата-центре российские сайты отдают 403, а живой парсинг в request-path
    # тормозит расчёт. Поэтому в проде ставим false: расчёт берёт только кэш
    # (его наполняет `python -m app.manage update_prices` с российского IP) и
    # seed-fallback. true — для локалки и самого обновлятора, где парсер работает.
    # Цены работ сеть на расчёте не трогают в любом случае (только чтение БД).
    PARSER_LIVE_FETCH: bool = True

    # Beta: headless-харвестер clearance-cookie DDoS-Guard для Мегастроя.
    # По умолчанию выключен — без него поведение прежнее (MEGASTROY_COOKIE
    # вручную или 403 -> seed). Требует patchright + chrome
    # (requirements-headless.txt), поэтому не включается по умолчанию, чтобы
    # не раздувать обязательные зависимости/образ.
    MEGASTROY_HEADLESS: bool = False

    # Beta: живой браузерный фетч каталога Лемана (#276). В отличие от
    # Мегастроя, cookie-харвест + requests тут не работает — Qrator ловит CDP
    # даже у headed настоящего Chrome без patchright. Поэтому это не харвест
    # cookie, а полноценный browser-fetch (app/parsers/leman_browser.py) через
    # patchright, и он же требует РФ-резидентный IP (не сработает в GCP US),
    # поэтому включаем только для ручного локального наполнения кэша цен.
    # По умолчанию выключен: fetch_price не ходит в сеть → seed-fallback.
    LEMAN_LIVE: bool = False

    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf8", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
settings = DBSettings()