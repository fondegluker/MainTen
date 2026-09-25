"""Database configuration and session management for CFMS with lazy engine initialization."""

from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

_engine: Any = None
_session_factory: Any = None

Base = declarative_base()


def get_engine():
    """Create and cache the SQLAlchemy engine lazily on first call."""
    global _engine
    if _engine is None:
        connect_args = {}
        if settings.DATABASE_URL.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
    return _engine


def get_session_factory():
    """Create and cache the sessionmaker factory lazily on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


def SessionLocal():
    """Callable session factory returning a new Session instance."""
    factory = get_session_factory()
    return factory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
