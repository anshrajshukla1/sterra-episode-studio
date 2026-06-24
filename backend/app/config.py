"""
app/config.py — Application configuration via environment variables.

Uses pydantic-settings so all settings are validated at startup.
Values can come from a .env file or real environment variables.
Environment variables always take priority over .env file values.
"""
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ─────────────────────────────────────────────────────────────
    # Must be an async-compatible URL: postgresql+asyncpg://...
    database_url: str = "sqlite+aiosqlite:///./stera.db"

    # ── File system paths ─────────────────────────────────────────────────────
    # Where uploaded/mounted .mcap recordings live
    recordings_dir: str = "/data/recordings"
    # Where the pipeline writes exported episode bundles
    episodes_dir: str = "/data/episodes"

    # ── Firebase ──────────────────────────────────────────────────────────────
    # The Firebase project ID is used to validate the `aud` claim on JWTs
    firebase_project_id: str = "dummy-project-id"

    # ── Security ──────────────────────────────────────────────────────────────
    # Internal secret key (not used for Firebase tokens, available for future use)
    secret_key: str = "dev-secret-key"

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Accepts either a JSON array string (from .env) or a Python list
    cors_origins: list[str] = [
        "http://localhost:5173",
        "https://stera-episode-studio.vercel.app",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """Allow CORS_ORIGINS to be supplied as a JSON string in .env files."""
        if isinstance(v, str):
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("cors_origins must be a JSON array of strings")
            return parsed
        return v  # type: ignore[return-value]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra env vars are silently ignored (safe for Docker envs with many vars)
        extra="ignore",
    )


# Module-level singleton — import this everywhere instead of instantiating Settings()
settings = Settings()
