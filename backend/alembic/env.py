"""
alembic/env.py — Alembic async migration environment.

Configured for use with SQLAlchemy asyncio + asyncpg (Neon PostgreSQL).

Key design choices:
- DATABASE_URL is loaded from the app's Settings object (reads .env),
  NOT from alembic.ini — keeps credentials in one place.
- The URL is converted from asyncpg→psycopg2 for Alembic's sync migration
  runner (Alembic doesn't natively support async drivers for DDL operations).
- `include_schemas=True` ensures foreign key enum types are picked up.
- target_metadata comes from app.database.Base, which imports all models
  via app.models — so autogenerate picks up all schema changes.

Usage:
    cd backend/
    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure the backend/ directory is on sys.path so we can import app.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

# Interpret the config file for Python logging (if alembic.ini defines loggers)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Load target metadata from our ORM models ─────────────────────────────────
# Importing app.models registers all ORM classes against Base.metadata.
from app.database import Base  # noqa: E402
from app import models  # noqa: F401, E402 — side-effect: registers all models

target_metadata = Base.metadata


# ── Database URL resolution ───────────────────────────────────────────────────

def get_sync_url() -> str:
    """
    Return a synchronous (psycopg2) URL for Alembic's migration runner.

    Alembic uses a synchronous engine internally for DDL operations.
    We convert the asyncpg URL to a psycopg2 URL:
      postgresql+asyncpg://...  →  postgresql+psycopg2://...

    The original async URL lives in Settings.database_url (loaded from .env).
    """
    from app.config import settings

    async_url = settings.database_url
    # Replace the asyncpg driver with psycopg2 for Alembic's sync engine
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    sync_url = sync_url.replace("postgres+asyncpg://", "postgresql+psycopg2://")
    # For local sqlite dev:
    sync_url = sync_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    return sync_url


# ── Migration modes ───────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    In this mode we configure the context with just a URL, not an engine.
    Calls to context.execute() emit the SQL to stdout instead of running it.
    Useful for generating migration SQL to review or run manually.
    """
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes in autogenerate
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates a synchronous engine and runs migrations against the live DB.
    This is what `alembic upgrade head` uses.
    """
    # Override the sqlalchemy.url in alembic.ini with our real URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pool for migrations — open/close immediately
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect column type changes in autogenerate
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
