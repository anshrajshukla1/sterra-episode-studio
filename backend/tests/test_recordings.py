"""
tests/test_recordings.py — Tests for recordings scan and upsert logic.

Tests cover:
1. Scan a temp directory with valid .mcap files → all discovered
2. Invalid .mcap files (wrong magic bytes) → skipped
3. Non-.mcap files in the directory → ignored
4. Re-scanning an already-known file → size update only (no duplicate)
5. Empty directory → empty list
6. GET /api/recordings requires auth → 401 without token

Uses pytest + pytest-asyncio + FastAPI TestClient (sync) for HTTP tests.
The recordings router's _scan_and_upsert is tested against an in-memory
SQLite database (via SQLAlchemy async) — no Postgres needed for unit tests.

SQLite is used instead of Postgres for tests because:
- No external DB needed in CI
- SQLAlchemy async works with aiosqlite for pure Python async
- Schema is simple enough that Postgres-specific types don't appear in tests
"""
import os
import sys
import tempfile
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── MCAP magic bytes constant ─────────────────────────────────────────────────
MCAP_MAGIC = b"\x89MCAP0\r\n"


# ── In-memory SQLite DB fixture for unit tests ────────────────────────────────

@pytest.fixture(scope="function")
async def async_db_session():
    """
    Provide an async SQLAlchemy session backed by an in-memory SQLite DB.

    Creates all tables fresh for each test function.
    Requires aiosqlite to be installed (add to test requirements if needed).
    """
    # Patch settings before importing app modules
    with patch.dict(os.environ, {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "FIREBASE_PROJECT_ID": "test-project",
        "SECRET_KEY": "test-secret",
        "RECORDINGS_DIR": "/tmp/test-recordings",
        "EPISODES_DIR": "/tmp/test-episodes",
    }):
        from app.database import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            # Import models to register them on Base.metadata
            from app import models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            yield session

        await engine.dispose()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_valid_mcap(path: str, extra_bytes: int = 64) -> str:
    """Write a valid MCAP file (correct magic bytes + padding) to path."""
    with open(path, "wb") as f:
        f.write(MCAP_MAGIC + b"\x00" * extra_bytes)
    return path


def make_invalid_mcap(path: str) -> str:
    """Write a file with wrong magic bytes to path."""
    with open(path, "wb") as f:
        f.write(b"\x00\x01\x02\x03\x04\x05\x06\x07" + b"\x00" * 64)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _scan_and_upsert
# ─────────────────────────────────────────────────────────────────────────────

class TestScanAndUpsert:
    """Tests for the _scan_and_upsert() function in routers/recordings.py."""

    @pytest.mark.asyncio
    async def test_discovers_valid_mcap_files(self, tmp_path, async_db_session):
        """Valid .mcap files should be inserted into the DB."""
        make_valid_mcap(str(tmp_path / "session_001.mcap"))
        make_valid_mcap(str(tmp_path / "session_002.mcap"))

        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert len(recordings) == 2
        filenames = {r.filename for r in recordings}
        assert "session_001.mcap" in filenames
        assert "session_002.mcap" in filenames

    @pytest.mark.asyncio
    async def test_skips_invalid_mcap_magic(self, tmp_path, async_db_session):
        """Files with wrong magic bytes should be skipped (not inserted)."""
        make_valid_mcap(str(tmp_path / "good.mcap"))
        make_invalid_mcap(str(tmp_path / "bad.mcap"))

        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert len(recordings) == 1
        assert recordings[0].filename == "good.mcap"

    @pytest.mark.asyncio
    async def test_ignores_non_mcap_files(self, tmp_path, async_db_session):
        """Non-.mcap files should be completely ignored."""
        make_valid_mcap(str(tmp_path / "valid.mcap"))
        (tmp_path / "notes.txt").write_text("not a recording")
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert len(recordings) == 1
        assert recordings[0].filename == "valid.mcap"

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path, async_db_session):
        """An empty directory should return an empty list."""
        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert recordings == []

    @pytest.mark.asyncio
    async def test_no_duplicate_on_rescan(self, tmp_path, async_db_session):
        """Scanning the same directory twice should not create duplicate rows."""
        make_valid_mcap(str(tmp_path / "once.mcap"))

        from app.routers.recordings import _scan_and_upsert

        # First scan
        first = await _scan_and_upsert(async_db_session, str(tmp_path))
        # Second scan of the same directory
        second = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert len(second) == 1
        assert first[0].id == second[0].id  # Same row, not a new one

    @pytest.mark.asyncio
    async def test_updates_size_on_rescan(self, tmp_path, async_db_session):
        """If a file's size changes between scans, size_bytes should update."""
        mcap_path = str(tmp_path / "growing.mcap")
        make_valid_mcap(mcap_path, extra_bytes=10)

        from app.routers.recordings import _scan_and_upsert

        first = await _scan_and_upsert(async_db_session, str(tmp_path))
        first_size = first[0].size_bytes

        # Overwrite with larger content
        make_valid_mcap(mcap_path, extra_bytes=1000)

        second = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert second[0].size_bytes > first_size
        assert second[0].size_bytes == 8 + 1000  # magic + padding

    @pytest.mark.asyncio
    async def test_nonexistent_directory(self, async_db_session):
        """Scanning a non-existent directory should return an empty list, not crash."""
        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, "/no/such/directory")

        assert recordings == []

    @pytest.mark.asyncio
    async def test_recording_initial_status_is_unprocessed(self, tmp_path, async_db_session):
        """Newly discovered recordings should have status='unprocessed'."""
        make_valid_mcap(str(tmp_path / "new.mcap"))

        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert recordings[0].status == "unprocessed"

    @pytest.mark.asyncio
    async def test_multiple_mcap_files_all_discovered(self, tmp_path, async_db_session):
        """All valid .mcap files in the directory should be discovered."""
        for i in range(5):
            make_valid_mcap(str(tmp_path / f"session_{i:03d}.mcap"))

        from app.routers.recordings import _scan_and_upsert

        recordings = await _scan_and_upsert(async_db_session, str(tmp_path))

        assert len(recordings) == 5


# ─────────────────────────────────────────────────────────────────────────────
# Tests: HTTP auth enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordingsAuthEnforcement:
    """Verify that auth is required — unauthenticated requests must return 401."""

    @pytest.fixture(autouse=True)
    def patch_settings_for_app(self):
        """Patch environment so app.config.Settings can initialise."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FIREBASE_PROJECT_ID": "test-project",
            "SECRET_KEY": "test-secret",
            "RECORDINGS_DIR": "/tmp/recordings",
            "EPISODES_DIR": "/tmp/episodes",
        }):
            yield

    def test_list_recordings_requires_auth(self):
        """GET /api/recordings without a token must return 401."""
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/recordings/")
        assert response.status_code == 401

    def test_get_recording_requires_auth(self):
        """GET /api/recordings/{id} without a token must return 401."""
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/recordings/some-id")
        assert response.status_code == 401

    def test_health_endpoint_is_public(self):
        """GET /health should return 200 without any token."""
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
