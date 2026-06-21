from pydantic import SecretStr  
from pydantic_settings import BaseSettings, SettingsConfigDict  
from pathlib import Path
ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"

class DBSettings(BaseSettings):  
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = "postgres"
    POSTGRES_DB: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf8", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
settings = DBSettings()