from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://shepherd:shepherd@localhost:5432/shepherd"

    # Browser origins allowed to call the API (the Angular dev server by default).
    # In .env: CORS_ORIGINS=["http://localhost:4200","https://app.example.org"]
    cors_origins: list[str] = ["http://localhost:4200", "http://127.0.0.1:4200"]

    # How many weeks ahead the worker keeps concrete Gathering rows generated.
    gathering_horizon_weeks: int = 12

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
