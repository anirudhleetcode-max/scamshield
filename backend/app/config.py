from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ScamShield"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "scamshield"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_body_bytes: int = 64_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
