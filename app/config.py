from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str
    webhook_base_url: str
    webhook_secret: str = ''
    web_host: str = '127.0.0.1'
    web_port: int = 3510
    db_path: str = 'data/app.db'
    log_level: str = 'INFO'
    default_timezone: str = 'Asia/Shanghai'
    telegram_api_id: int = 0
    telegram_api_hash: str = ''
    session_encryption_key: str = ''
    send_min_interval_seconds: int = 3

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}/telegram"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]


settings = Settings()
