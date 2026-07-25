from configparser import ConfigParser
from functools import lru_cache
from os import getenv
from pathlib import Path
from typing import Any

from pydantic import BaseModel

CONFIG_FILE_ENV = "AIHR_CONFIG_FILE"
ENV_PREFIX = "AIHR_"
DEFAULT_CONFIG_FILE = Path("config/config.ini")


class Settings(BaseModel):
    app_name: str = "AIHR Analytics"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./aihr.db"
    api_url: str = "http://localhost:8000/api/v1"
    api_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:8501"
    seed_demo_data: bool = True
    mysql_database: str = "aihr"
    mysql_user: str = "aihr"
    mysql_password: str = "local_demo_password"
    mysql_root_password: str = "local_demo_root_password"

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
}


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


def load_settings(config_file: Path | None = None) -> Settings:
    resolved_config_file = config_file or _resolve_config_file()
    values: dict[str, Any] = {}
    values.update(_load_ini_settings(resolved_config_file))
    values.update(_load_env_settings())
    return Settings(**values)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
