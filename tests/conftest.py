import os

os.environ["AIHR_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AIHR_ENVIRONMENT"] = "test"
os.environ["AIHR_SEED_DEMO_DATA"] = "true"
