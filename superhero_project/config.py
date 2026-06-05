"""Application settings loaded from environment variables (or a .env file)."""

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    github_client_id: str
    github_client_secret: str
    session_secret: str
    https_only: bool = False
    base_url: str = "http://localhost:8000"


settings = Settings()
