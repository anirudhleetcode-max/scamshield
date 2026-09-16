import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PLACEHOLDER_SECRETS = {"", "change-me-in-production", "replace-with-a-long-random-string", "secret", "changeme"}
MIN_SECRET_LEN = 32
log = logging.getLogger("scamshield.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    app_name: str = "ScamShield"
    env: str = "development"  # development | test | production
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "scamshield"
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_body_bytes: int = 64_000
    model_dir: str = str(BACKEND_DIR / "models")
    model_version: str = "2.0.0"
    inference_timeout_s: float = 10.0
    login_max_attempts: int = 10
    login_window_s: int = 300
    log_level: str = "INFO"


def check_jwt_secret(s: Settings) -> Settings:
    """Refuse a placeholder / short secret in production; in dev/test generate an ephemeral one."""
    weak = s.jwt_secret in PLACEHOLDER_SECRETS or len(s.jwt_secret) < MIN_SECRET_LEN
    if not weak:
        return s
    if s.env == "production":
        raise RuntimeError(
            "JWT_SECRET is missing, a placeholder or shorter than 32 chars. Generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` and set it in .env")
    log.warning("JWT_SECRET is weak or unset (ENV=%s): using an ephemeral random secret - "
                "sessions will not survive a restart", s.env)
    s.jwt_secret = secrets.token_urlsafe(48)
    return s


@lru_cache
def get_settings() -> Settings:
    return check_jwt_secret(Settings())
