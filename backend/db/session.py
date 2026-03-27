"""
SQLAlchemy session factories — async for FastAPI, sync for Celery/CLI.

Uses SQLite for local dev, Postgres in production (controlled by DATABASE_URL).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

from backend.config import settings


class Base(DeclarativeBase):
    pass


# ── Sync engine (Celery workers, CLI commands) ──────────────────
def _sync_url() -> str:
    url = settings.database_url
    # SQLite: use as-is
    if url.startswith("sqlite"):
        return url
    # Postgres: strip async driver if present
    return url.replace("postgresql+asyncpg://", "postgresql://")


sync_engine = create_engine(_sync_url(), echo=(settings.app_env == "development"))
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


def get_sync_db() -> Session:
    """Yield a sync DB session."""
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── Async engine (FastAPI) — only if asyncpg is available ───────
try:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    def _async_url() -> str:
        url = settings.database_url
        if url.startswith("sqlite"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        return url.replace("postgresql://", "postgresql+asyncpg://")

    async_engine = create_async_engine(_async_url(), echo=(settings.app_env == "development"))
    AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def get_db() -> AsyncSession:
        """FastAPI dependency — yields an async DB session per request."""
        async with AsyncSessionLocal() as session:
            yield session

except ImportError:
    # asyncpg/aiosqlite not installed — async endpoints won't work
    # but sync CLI and Celery tasks will
    pass
