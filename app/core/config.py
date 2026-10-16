
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "My Farm Grows"
    debug: bool = True
    database_url: str = "postgresql+psycopg://postgres:123456789@localhost:5432/myfarmgrows"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
