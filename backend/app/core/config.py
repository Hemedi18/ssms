from typing import List, Optional
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

    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "hemy@2004"

    # AI & Google AI Studio (Gemini) Settings
    GEMINI_API_KEY: Optional[str] = None
    AI_AUTO_REPLY_ENABLED: bool = True
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    AI_SYSTEM_PROMPT: str = (
        "Wewe ni msaidizi mahiri wa SMS wa biashara yetu. "
        "Jibu kwa lugha ileile ya mteja (Kiswahili au Kiingereza). "
        "Toa majibu mafupi, yenye heshima, na kueleweka moja kwa moja (yasizidi herufi 160 inapowezekana, ukomo herufi 300). "
        "USITUMIE alama za markdown (kama nyota *, herufi nene, vichwa vya habari #, au bullet points) "
        "kwa sababu ujumbe huu unatumwa kama SMS ya kawaida kwenye simu ya mkononi."
    )
    AI_MAX_OUTPUT_TOKENS: int = 300
    AI_TEMPERATURE: float = 0.7
    AI_REPLY_SENDER_NAME: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
