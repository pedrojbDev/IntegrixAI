from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""

    pass


def get_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = int(settings.db_connect_timeout_seconds)
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
