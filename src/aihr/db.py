"""Compatibility exports for the canonical database module."""

from aihr.database import Base, create_engine_and_session, get_db

__all__ = ["Base", "create_engine_and_session", "get_db"]
