from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/orientador_usil"
    )
    whatsapp_provider: str = "pywhatkit"
    whatsapp_dry_run: bool = True
    whatsapp_wait_time: int = 20
    whatsapp_close_time: int = 3
    bridge_send_url: str = "http://127.0.0.1:3001/send"
    bridge_send_timeout: int = 60
    inbound_api_key: str = ""
    portal_oficial_url: str = "https://www.usil.edu.pe/"
    llm_provider: str = "ollama"
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:0.8b"
    ollama_think: bool = False
    ollama_temperature: float = 0.2
    ollama_max_tokens: int = 400
    ollama_timeout: int = 120

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
