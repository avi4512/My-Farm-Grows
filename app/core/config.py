from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never be used as a real secret.
_PLACEHOLDER_SECRETS = {"changeme", "change-me", "secret", "your-secret-key"}


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env.

    DATABASE_URL and JWT_SECRET_KEY are required: the application refuses
    to start without them instead of falling back to insecure defaults.
    """

    app_name: str = "My Farm Grows"
    debug: bool = False

    database_url: str = Field(min_length=1)

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def reject_placeholder_secret(cls, value: str) -> str:
        if value.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError("JWT_SECRET_KEY must not be a placeholder value")
        return value


settings = Settings()
