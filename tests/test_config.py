from pathlib import Path

from aihr.config import load_settings


def test_loads_settings_from_ini_file() -> None:
    settings = load_settings(Path("config/config.Test.ini"))

    assert settings.environment == "test"
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.seed_demo_data is True


def test_environment_overrides_ini_file(monkeypatch) -> None:
    monkeypatch.setenv("AIHR_DATABASE_URL", "sqlite+pysqlite:///override.db")

    settings = load_settings(Path("config/config.Test.ini"))

    assert settings.database_url == "sqlite+pysqlite:///override.db"
