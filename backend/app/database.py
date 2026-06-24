"""
app/database.py — Async SQLAlchemy engine, session factory, and helpers.

Design notes:
- Uses asyncpg driver (postgresql+asyncpg) for non-blocking DB I/O
- pool_pre_ping=True: verifies connection health before use (prevents
  stale connection errors with Neon's aggressive idle timeouts)
- expire_on_commit=False: prevents lazy-load AttributeErrors after commit
  in async context (async session can't issue sync I/O for lazy loads)
- Base is defined here and imported by models.py to avoid circular imports
"""
import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

from sqlalchemy.pool import NullPool

# ── Engine ────────────────────────────────────────────────────────────────────
if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # See design note above
)


# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All ORM models inherit from this class."""
    pass


# ── DB lifecycle ──────────────────────────────────────────────────────────────
async def init_db() -> None:
    """
    Create all tables defined in ORM models.

    Called once at application startup (via lifespan).
    For production migrations use Alembic instead — this function is a
    development convenience that ensures tables exist on first run.
    """
    async with engine.begin() as conn:
        # Import models here to ensure they are registered on Base.metadata
        # before create_all is called. The noqa suppresses the "imported but
        # unused" linter warning — the side-effect (registration) is the goal.
        from app import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialised")


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:  # type: ignore[return]
    """
    Yield an AsyncSession for use in route handlers.

    Usage:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        yield session
