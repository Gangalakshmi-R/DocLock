"""Database engine, session factory and declarative base."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config

_connect_args = {"check_same_thread": False} if str(config.DATABASE_CONNECTION).startswith("sqlite") else {}
engine = create_engine(config.DATABASE_CONNECTION, pool_pre_ping=True, pool_recycle=1800, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    """Naive UTC timestamp (matches the existing TIMESTAMP-without-timezone columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
