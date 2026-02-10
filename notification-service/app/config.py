from typing import List, Optional

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Service configuration
    SERVICE_NAME: str = "notification-service"
    SERVICE_PORT: int = 8004
    ENVIRONMENT: str = "development"
    APP_VERSION: str = "1.0.0"

    # Database configuration
    DATABASE_URL: str  # required — no insecure default

    # Database connection pool
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10

    # HTTP client
    HTTP_CLIENT_TIMEOUT: float = 10.0

    # Health-check thresholds (percent)
    HEALTH_MEMORY_THRESHOLD: float = 90.0
    HEALTH_DISK_THRESHOLD: float = 90.0

    # CORS
    CORS_ORIGINS: str = "http://localhost:8080,http://localhost:3000"

    # External service URLs
    INCIDENT_SERVICE_URL: Optional[str] = "http://incident-management:8002"
    ONCALL_SERVICE_URL: Optional[str] = "http://oncall-service:8003"
    ALERT_SERVICE_URL: Optional[str] = "http://alert-ingestion:8001"
    NOTIFICATION_SERVICE_URL: Optional[str] = "http://notification-service:8004"

    # Notification channels — SMTP email
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_SENDER: str = "omarafidi2005@gmail.com"
    SMTP_PASSWORD: Optional[str] = "epce wqco bsgw zssm"
    EMAIL_COOLDOWN_SECONDS: int = 10  # Max 1 email per engineer every 10 seconds
    WEBHOOK_URLS: str = ""  # Comma-separated webhook URLs
    SLACK_WEBHOOK_URL: Optional[str] = None  # From env only — never hardcode

    # SendGrid email (alternative to SMTP)
    SENDGRID_API_KEY: Optional[str] = None  # From env only — never hardcode
    SENDGRID_FROM_EMAIL: str = "noreply@incident-platform.local"

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def webhook_url_list(self) -> List[str]:
        return [u.strip() for u in self.WEBHOOK_URLS.split(",") if u.strip()]

    model_config = ConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
