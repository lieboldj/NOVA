from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "sqlite:///./.data/nova.db"
    storage_path: Path = Path(".data/documents")
    storage_bucket: str = ""
    nova_reviewer_token: SecretStr = SecretStr("")
    nova_automation_token: SecretStr = SecretStr("")
    nova_reviewer_name: str = "local-reviewer"
    nova_cookie_secure: bool = False
    nova_session_cookie: str = "nova_review"
    frontend_dist: Path = Path("dist")
    ai_mode: Literal["gemini", "fixture"] = "gemini"
    anonymizer_mode: Literal["anymize", "fixture"] = "anymize"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.6-flash"
    anymize_api_key: SecretStr = SecretStr("")
    anymize_base_url: str = "https://app.anymize.ai/api"
    anymize_poll_seconds: float = 2
    anymize_timeout_seconds: float = 120
    mail_mode: Literal["simulation", "smtp", "gmail"] = "simulation"
    gmail_mailbox: str = "devstar4415@gcplab.me"
    gmail_supplier: str = "devstar4418@gcplab.me"
    gmail_client_id: SecretStr = SecretStr("")
    gmail_client_secret: SecretStr = SecretStr("")
    gmail_refresh_token: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    smtp_starttls: bool = True
    response_days: int = 7
    max_reminders: int = 2
    upload_limit_bytes: int = 10 * 1024 * 1024
    import_limit_bytes: int = 64 * 1024 * 1024
    worker_poll_seconds: float = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
