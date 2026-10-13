from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LED Ops"
    environment: str = "development"
    secret_key: SecretStr = SecretStr("development-only-secret-key-change-me")
    access_token_expire_minutes: int = 480
    database_url: str = "postgresql+asyncpg://ledops:ledops@localhost:5432/ledops"
    redis_url: str = "redis://localhost:6379/0"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    telegram_webhook_secret: SecretStr | None = None
    max_webhook_secret: SecretStr | None = None

    @model_validator(mode="after")
    def reject_default_production_secret(self) -> "Settings":
        if (
            self.environment.casefold() == "production"
            and self.secret_key.get_secret_value() == "development-only-secret-key-change-me"
        ):
            raise ValueError("SECRET_KEY must be replaced in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
