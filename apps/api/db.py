"""
SQLAlchemy engine/session wiring. Swap the connection string via
DATABASE_URL; schema changes go through Alembic (apps/api/migrations/,
apps/api/alembic.ini) rather than Base.metadata.create_all() outside of
tests — see docs/TODO.md's "Database migrations" section in README.md.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
