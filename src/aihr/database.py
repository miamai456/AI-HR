from collections.abc import Generator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def create_engine_and_session(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    if database_url.startswith("sqlite"):
        url = make_url(database_url)
        database_path = url.database
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False}
        pool_options = {"poolclass": StaticPool} if database_path == ":memory:" else {}
    else:
        connect_args = {}
        pool_options = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 10,
            "pool_recycle": 1800,
        }

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        **pool_options,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, session_factory


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session
