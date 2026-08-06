from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartFoodIA"
    app_version: str = "0.0.4"
    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "postgresql+psycopg://smartfoodia:change-me@db:5432/smartfoodia"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_timeout_seconds: float = 45.0
    olivia_max_tool_rounds: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
