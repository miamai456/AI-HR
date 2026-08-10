from pathlib import Path

from sqlalchemy.engine.url import make_url

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


def test_cache_and_prewarm_settings_can_be_injected(monkeypatch) -> None:
    monkeypatch.setenv("AIHR_CACHE_URL", "redis://cache:6379/0")
    monkeypatch.setenv("AIHR_ANALYSIS_PREWARM", "true")
    monkeypatch.setenv("AIHR_ANALYSIS_QUEUE_ENABLED", "true")

    settings = load_settings(Path("config/config.Test.ini"))

    assert settings.cache_url == "redis://cache:6379/0"
    assert settings.analysis_prewarm is True
    assert settings.analysis_queue_enabled is True


def test_observability_settings_can_be_injected(monkeypatch) -> None:
    monkeypatch.setenv("AIHR_OPERATIONS_TOKEN_FILE", "E:/AIHRData/secrets/token")
    monkeypatch.setenv("AIHR_OTEL_EXPORTER_ENDPOINT", "http://otel:4318")

    settings = load_settings(Path("config/config.Test.ini"))

    assert settings.operations_token_file == "E:/AIHRData/secrets/token"
    assert settings.otel_exporter_endpoint == "http://otel:4318"


def test_database_and_assistant_secrets_can_be_loaded_from_files(
    monkeypatch,
    tmp_path,
) -> None:
    database_secret = tmp_path / "postgres_password"
    database_secret.write_text("p@ssword", encoding="utf-8")
    assistant_secret = tmp_path / "deepseek_api_key"
    assistant_secret.write_text("secret-key", encoding="utf-8")
    monkeypatch.setenv(
        "AIHR_DATABASE_URL",
        "postgresql+psycopg://aihr@postgres:5432/aihr",
    )
    monkeypatch.setenv("AIHR_DATABASE_PASSWORD_FILE", str(database_secret))
    monkeypatch.setenv("AIHR_ASSISTANT_API_KEY_FILE", str(assistant_secret))

    settings = load_settings(Path("config/config.Test.ini"))

    assert make_url(settings.database_url).password == "p@ssword"
    assert settings.assistant_api_key == "secret-key"


def test_missing_assistant_secret_file_keeps_direct_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIHR_ASSISTANT_API_KEY", "direct-key")
    monkeypatch.setenv(
        "AIHR_ASSISTANT_API_KEY_FILE",
        str(tmp_path / "missing"),
    )

    settings = load_settings(Path("config/config.Test.ini"))

    assert settings.assistant_api_key == "direct-key"
