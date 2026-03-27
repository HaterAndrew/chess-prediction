"""
Application configuration loaded from environment variables.
Never hardcode credentials — use a .env file locally or secrets manager in prod.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///data/chess_predictor.db"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Scraper credentials (provided by tournament director)
    cca_username: str = ""
    cca_password: str = ""

    # Notification providers (Phase 1: email only)
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    twilio_account_sid: str = ""   # Phase 4
    twilio_auth_token: str = ""    # Phase 4
    twilio_from_number: str = ""   # Phase 4

    # App
    app_env: str = "development"   # development | production
    secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    # CCA day boundary — CCA resets daily counts at 2000 ET.
    # Canonical scrape at 2015 ET captures the full closed day.
    # Intra-day data comes from manual "Refresh" button, not scheduled scrapes.
    cca_day_close_hour: int = 20         # 2000 ET (8 PM)
    cca_day_close_minute: int = 0
    canonical_scrape_hour: int = 20      # 2015 ET
    canonical_scrape_minute: int = 15
    cca_timezone: str = "America/New_York"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
