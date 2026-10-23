from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SIM SMS Gateway"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    SECRET_KEY: str = "change-me-to-a-secure-random-secret-key-in-production"
    DATABASE_URL: str = "sqlite:///./sms_gateway.db"
    ALLOWED_ORIGINS: List[str] = ["*"]

    # SMS & Gateway Controls
    DEFAULT_COUNTRY_CODE: str = "+255"
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_MESSAGE_LENGTH: int = 1600
    RECIPIENT_ALLOWLIST: List[str] = []

    # Webhook Config
    WEBHOOK_MAX_RETRIES: int = 5
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_ALLOW_LOCAL_URLS: bool = False

    # Device & Job Leasing
    JOB_LEASE_TIMEOUT_SECONDS: int = 120
    DEVICE_OFFLINE_THRESHOLD_SECONDS: int = 180
    PAIRING_CODE_EXPIRE_SECONDS: int = 600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
