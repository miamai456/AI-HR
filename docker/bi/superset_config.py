import os


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


SECRET_KEY = env("SUPERSET_SECRET_KEY", "local-demo-superset-secret")

SQLALCHEMY_DATABASE_URI = (
    "sqlite:////app/superset_home/superset.db"
)

REDIS_HOST = env("REDIS_HOST", "superset-redis")
REDIS_PORT = int(env("REDIS_PORT", "6379"))

CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}

DATA_CACHE_CONFIG = CACHE_CONFIG
