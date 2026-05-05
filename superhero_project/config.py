from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    github_client_id: str
    github_client_secret: str
    session_secret: str
    base_url: str = "http://localhost:8000"


settings = Settings()
