from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AIHR Analytics"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./aihr.db"
    api_url: str = "http://localhost:8000/api/v1"
    api_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:8501"
    seed_demo_data: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AIHR_",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
