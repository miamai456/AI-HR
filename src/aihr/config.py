from configparser import ConfigParser
from functools import lru_cache
from os import getenv
from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, model_validator
from sqlalchemy.engine.url import make_url

CONFIG_FILE_ENV = "AIHR_CONFIG_FILE"
ENV_PREFIX = "AIHR_"
DEFAULT_CONFIG_FILE = Path("config/config.ini")


class Settings(BaseModel):
    app_name: str = "AIHR Analytics"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./aihr.db"
    database_password_file: str = ""
    api_url: str = "http://localhost:8000/api/v1"
    api_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:8501"
    seed_demo_data: bool = True
    mysql_database: str = "aihr"
    mysql_user: str = "aihr"
    mysql_password: str = "local_demo_password"
    mysql_root_password: str = "local_demo_root_password"
    postgres_database: str = "aihr"
    postgres_user: str = "aihr"
    postgres_password: str = ""
    mongo_url: str = ""
    mongo_database: str = "aihr_documents"
    synthetic_seed_recommendations: int = 100_000
    synthetic_seed_candidates: int = 80_000
    synthetic_seed_jobs: int = 1_500
    synthetic_seed: int = 20260722
    assistant_provider: str = "deepseek"
    assistant_base_url: str = "https://api.deepseek.com"
    assistant_model: str = "deepseek-chat"
    assistant_api_key: str = ""
    assistant_api_key_file: str = ""
    assistant_cache_ttl_seconds: int = 60
    assistant_max_attempts: int = 3
    cache_url: str = ""
    cache_prefix: str = "aihr"
    analysis_context_cache_ttl_seconds: int = 300
    analysis_prewarm: bool = False
    analysis_queue_enabled: bool = False
    analysis_queue_name: str = "aihr"
    operations_token: str = ""
    operations_token_file: str = ""
    otel_exporter_endpoint: str = ""
    otel_service_name: str = "aihr-api"

    @model_validator(mode="after")
    def resolve_runtime_settings(self):
        url = make_url(self.database_url)
        if url.drivername == "postgresql":
            self.database_url = url.set(drivername="postgresql+psycopg").render_as_string(
                hide_password=False
            )
        if self.assistant_api_key_file:
            file_api_key = _read_secret_file(self.assistant_api_key_file)
            if file_api_key:
                self.assistant_api_key = file_api_key
        if self.database_password_file:
            password = _read_secret_file(self.database_password_file)
            if password:
                url = make_url(self.database_url)
                if url.get_backend_name() == "postgresql":
                    self.database_url = url.set(password=password).render_as_string(
                        hide_password=False
                    )
                    self.postgres_password = password
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


SECTION_KEY_ALIASES = {
    ("app", "name"): "app_name",
    ("app", "app_name"): "app_name",
    ("app", "environment"): "environment",
    ("app", "api_public_url"): "api_public_url",
    ("app", "cors_origins"): "cors_origins",
    ("app", "seed_demo_data"): "seed_demo_data",
    ("database", "url"): "database_url",
    ("database", "database_url"): "database_url",
    ("dashboard", "api_url"): "api_url",
    ("mysql", "database"): "mysql_database",
    ("mysql", "user"): "mysql_user",
    ("mysql", "password"): "mysql_password",
    ("mysql", "root_password"): "mysql_root_password",
    ("postgres", "database"): "postgres_database",
    ("postgres", "user"): "postgres_user",
    ("postgres", "password"): "postgres_password",
    ("mongodb", "url"): "mongo_url",
    ("mongodb", "database"): "mongo_database",
    ("synthetic", "seed_recommendations"): "synthetic_seed_recommendations",
    ("synthetic", "seed_candidates"): "synthetic_seed_candidates",
    ("synthetic", "seed_jobs"): "synthetic_seed_jobs",
    ("synthetic", "seed"): "synthetic_seed",
}


def _read_secret_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_config_file() -> Path:
    configured_file = Path(getenv(CONFIG_FILE_ENV, str(DEFAULT_CONFIG_FILE)))
    if configured_file.is_absolute():
        return configured_file

    cwd_file = Path.cwd() / configured_file
    if cwd_file.exists():
        return cwd_file

    return _project_root() / configured_file


def _load_ini_settings(config_file: Path) -> dict[str, str]:
    if not config_file.exists():
        return {}

    parser = ConfigParser()
    parser.read(config_file, encoding="utf-8")
    values: dict[str, str] = {}
    setting_fields = set(Settings.model_fields)

    for key, value in parser.defaults().items():
        if key in setting_fields:
            values[key] = value

    for section in parser.sections():
        for key, value in parser.items(section):
            setting_name = SECTION_KEY_ALIASES.get((section.lower(), key.lower()), key)
            if setting_name in setting_fields:
                values[setting_name] = value

    return values


def _load_env_settings() -> dict[str, str]:
    values: dict[str, str] = {}
    for field in Settings.model_fields:
        env_value = getenv(f"{ENV_PREFIX}{field.upper()}")
        if env_value is not None:
            values[field] = env_value
    return values


def _load_local_assistant_settings() -> dict[str, str]:
    secrets_file = _project_root() / ".streamlit" / "secrets.toml"
    if not secrets_file.exists():
        return {}
    try:
        values = tomllib.loads(secrets_file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    aliases = {
        "AIHR_ASSISTANT_PROVIDER": "assistant_provider",
        "AIHR_ASSISTANT_BASE_URL": "assistant_base_url",
        "AIHR_ASSISTANT_MODEL": "assistant_model",
        "AIHR_ASSISTANT_API_KEY": "assistant_api_key",
    }
    return {
        setting_name: str(values[key])
        for key, setting_name in aliases.items()
        if values.get(key)
    }


def load_settings(config_file: Path | None = None) -> Settings:
    resolved_config_file = config_file or _resolve_config_file()
    values: dict[str, Any] = {}
    values.update(_load_ini_settings(resolved_config_file))
    values.update(_load_local_assistant_settings())
    values.update(_load_env_settings())
    return Settings(**values)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
