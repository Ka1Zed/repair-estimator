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

    # Ходить ли в живой парсер материалов при расчёте сметы. На сервере в
    # дата-центре российские сайты отдают 403, а живой парсинг в request-path
    # тормозит расчёт. Поэтому в проде ставим false: расчёт берёт только кэш
    # (его наполняет `python -m app.manage update_prices` с российского IP) и
    # seed-fallback. true — для локалки и самого обновлятора, где парсер работает.
    # Цены работ сеть на расчёте не трогают в любом случае (только чтение БД).
    PARSER_LIVE_FETCH: bool = True

    # Beta: headless-харвестер clearance-cookie DDoS-Guard для Мегастроя
    # (plans/2026-06-30-beta-headless-parser.md). По умолчанию выключен — без
    # него поведение прежнее (MEGASTROY_COOKIE вручную или 403 -> seed).
    # Требует playwright + chromium (requirements-headless.txt), поэтому не
    # включается по умолчанию, чтобы не раздувать обязательные зависимости/образ.
    MEGASTROY_HEADLESS: bool = False

    # Beta: headless-харвестер cookie для Лемана (#276), тот же принцип, что у
    # Мегастроя выше — по умолчанию выключен, требует playwright + chromium.
    LEMAN_HEADLESS: bool = False

    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf8", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
settings = DBSettings()