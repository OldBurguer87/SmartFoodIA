from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartFoodIA"
    app_version: str = "0.3.3"
    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "postgresql+psycopg://smartfoodia:change-me@db:5432/smartfoodia"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_timeout_seconds: float = 45.0
    olivia_max_tool_rounds: int = 8
    whatsapp_access_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_app_secret_previous: str | None = None
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_timeout_seconds: float = 30.0
    payment_receipt_storage_path: str = "/data/receipts"
    payment_receipt_max_bytes: int = 10_485_760
    payment_receipt_retention_days: int = 15
    payment_receipt_retention_interval_seconds: int = 3600
    pix_receipt_fingerprint_secret: str | None = None
    pix_receipt_min_ai_confidence: float = 0.90
    channel_worker_poll_seconds: float = 2.0
    channel_worker_batch_size: int = 50
    channel_worker_max_attempts: int = 5
    human_wait_reminder_seconds: int = 120
    human_wait_timeout_seconds: int = 300
    auth_cookie_name: str = "smartfoodia_session"
    auth_session_hours: int = 12
    auth_cookie_secure: bool = True
    auth_cookie_samesite: str = "lax"
    frontend_origin: str = "http://localhost:3000"
    public_domain: str | None = None
    public_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
