from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    db_mode: str = "local"
    database_url: str = (
        "postgresql+psycopg2://usil:usil@localhost:5432/usil_db"
    )
    whatsapp_provider: str = "bridge"
    whatsapp_dry_run: bool = True
    whatsapp_wait_time: int = 20
    whatsapp_close_time: int = 3
    bridge_send_url: str = "http://127.0.0.1:3001/send"
    bridge_send_timeout: int = 60
    inbound_api_key: str = ""
    portal_oficial_url: str = "https://www.usil.edu.pe/"
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
