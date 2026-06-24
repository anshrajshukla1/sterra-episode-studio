"""
tests/test_pipeline.py — Unit tests for pipeline.py.

Tests cover:
1. validate_mcap_file — valid magic bytes, invalid bytes, empty file, unreadable
2. _inspect_streams — with mocked SDK session objects
3. run_pipeline — full mock of stera-sdk (no real SDK needed)

All stera-sdk imports are mocked so these tests run without the SDK installed.
Uses pytest-asyncio for async test support.

Design:
- The stera-sdk modules are injected via sys.modules mock so the lazy
  imports inside pipeline.py (deferred inside executor lambdas) are intercepted.
- emit() is a simple list-appending mock to capture log lines.
- PipelineResult and PipelineError are tested as first-class objects.
"""
import asyncio
import io
import sys
import os
import tempfile
import types
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ── Import the module under test ──────────────────────────────────────────────
from app.pipeline import (
    PipelineError,
    PipelineResult,
    _inspect_streams,
    validate_mcap_file,
)

# ── Constants ─────────────────────────────────────────────────────────────────
MCAP_MAGIC = b"\x89MCAP0\r\n"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: validate_mcap_file
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateMcapFile:
    """Tests for the validate_mcap_file() helper."""

    def test_valid_mcap_magic_bytes(self, tmp_path):
        """A file with correct MCAP magic bytes should return (True, '')."""
        f = tmp_path / "valid.mcap"
        # Write magic + some dummy content
        f.write_bytes(MCAP_MAGIC + b"\x00" * 100)

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is True
        assert err == ""

    def test_invalid_magic_bytes(self, tmp_path):
        """A file with wrong magic bytes should return (False, <message>)."""
        f = tmp_path / "bad.mcap"
        f.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07" + b"\x00" * 100)

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is False
        assert "magic bytes mismatch" in err.lower()
        # Error should include the hex representation for debugging
        assert "0001020304050607" in err

    def test_empty_file(self, tmp_path):
        """An empty file is too small to contain MCAP magic bytes."""
        f = tmp_path / "empty.mcap"
        f.write_bytes(b"")

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is False
        assert "too small" in err.lower()

    def test_file_smaller_than_8_bytes(self, tmp_path):
        """A 4-byte file is too small — magic is 8 bytes."""
        f = tmp_path / "tiny.mcap"
        f.write_bytes(b"\x89MCA")  # 4 bytes — truncated magic

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is False
        assert "too small" in err.lower()

    def test_nonexistent_file(self):
        """A path that doesn't exist should return (False, <message>)."""
        is_valid, err = validate_mcap_file("/nonexistent/path/to/file.mcap")

        assert is_valid is False
        assert "cannot read file" in err.lower()

    def test_exactly_8_bytes_valid(self, tmp_path):
        """A file that is exactly the 8 magic bytes — minimum valid."""
        f = tmp_path / "minimal.mcap"
        f.write_bytes(MCAP_MAGIC)

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is True
        assert err == ""

    def test_pdf_file_rejected(self, tmp_path):
        """A PDF file (common wrong-file mistake) should be rejected."""
        f = tmp_path / "wrong.mcap"
        f.write_bytes(b"%PDF-1.4" + b"\x00" * 100)  # PDF magic bytes

        is_valid, err = validate_mcap_file(str(f))

        assert is_valid is False
        assert "magic bytes mismatch" in err.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _inspect_streams
# ─────────────────────────────────────────────────────────────────────────────

class TestInspectStreams:
    """Tests for _inspect_streams() with mocked SDK session objects."""

    def test_modern_sdk_with_all_streams(self):
        """Modern SDK with rgb, depth, pose streams."""
        session = MagicMock()
        session.stream_info.return_value = {
            "rgb": {"fps": 30},
            "depth": {"fps": 15},
            "pose": {"frequency": 100},
        }
        session.frame_count.return_value = 5400
        session.duration.return_value = 180.0

        result = _inspect_streams(session)

        assert "rgb" in result
        assert "depth" in result
        assert "pose" in result
        assert result["frame_count"] == 5400
        assert result["duration_s"] == 180.0

    def test_modern_sdk_rgb_only(self):
        """Recording with only an RGB stream (no depth, no pose)."""
        session = MagicMock()
        session.stream_info.return_value = {"rgb": {"fps": 30}}
        session.frame_count.return_value = 1800
        session.duration.return_value = 60.0

        result = _inspect_streams(session)

        assert "rgb" in result
        assert "depth" not in result
        assert "pose" not in result
        assert result["frame_count"] == 1800
        assert result["duration_s"] == 60.0

    def test_older_sdk_without_stream_info(self):
        """Older SDK that raises AttributeError on stream_info()."""
        session = MagicMock()
        session.stream_info.side_effect = AttributeError("no stream_info")
        session.frame_count.return_value = 100
        session.duration.return_value = 3.3

        # Should not raise — graceful fallback
        result = _inspect_streams(session)

        assert result["frame_count"] == 100
        assert result["duration_s"] == pytest.approx(3.3)

    def test_sdk_without_frame_count(self):
        """SDK without frame_count() falls back to 0."""
        session = MagicMock()
        session.stream_info.return_value = {"rgb": {}}
        session.frame_count.side_effect = AttributeError
        session.duration.return_value = 10.0

        result = _inspect_streams(session)

        assert result["frame_count"] == 0

    def test_sdk_without_duration(self):
        """SDK without duration() falls back to 0.0."""
        session = MagicMock()
        session.stream_info.return_value = {"rgb": {}}
        session.frame_count.return_value = 300
        session.duration.side_effect = AttributeError

        result = _inspect_streams(session)

        assert result["duration_s"] == 0.0

    def test_empty_stream_info(self):
        """Empty stream_info dict — no streams found."""
        session = MagicMock()
        session.stream_info.return_value = {}
        session.frame_count.return_value = 0
        session.duration.return_value = 0.0

        result = _inspect_streams(session)

        assert result["frame_count"] == 0
        assert "rgb" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_pipeline (fully mocked stera-sdk)
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_stera_modules():
    """
    Build a minimal mock of the stera-sdk module tree.

    Returns a dict suitable for patching into sys.modules.
    """
    # stera.data.MCAPReader mock
    mock_frame = MagicMock()
    mock_frame.index = 0

    mock_session = MagicMock()
    mock_session.stream_info.return_value = {
        "rgb": {"fps": 30},
        "depth": {"fps": 15},
        "pose": {"frequency": 100},
    }
    mock_session.frame_count.return_value = 3  # Small for fast tests
    mock_session.duration.return_value = 0.1
    mock_session.frames.return_value = iter([mock_frame, mock_frame, mock_frame])
    mock_session.export = MagicMock()
    mock_session.add_rgb_frame = MagicMock()
    mock_session.add_hand_pose = MagicMock()

    mock_mcap_reader_cls = MagicMock(return_value=mock_session)

    mock_data = types.ModuleType("stera.data")
    mock_data.MCAPReader = mock_mcap_reader_cls

    # stera.models.FaceBlurrer mock
    mock_blurrer = MagicMock()
    mock_blurrer.blur.return_value = MagicMock()  # clean_frame

    mock_face_blurrer_cls = MagicMock(return_value=mock_blurrer)

    mock_models = types.ModuleType("stera.models")
    mock_models.FaceBlurrer = mock_face_blurrer_cls
    mock_models.HandTracker = MagicMock()

    # stera.Evaluate mock
    mock_report = MagicMock()
    mock_report.health_score = 0.87
    mock_report.save = MagicMock()

    mock_evaluate_cls = MagicMock(return_value=mock_report)

    mock_stera = types.ModuleType("stera")
    mock_stera.Evaluate = mock_evaluate_cls
    mock_stera.data = mock_data
    mock_stera.models = mock_models

    return {
        "stera": mock_stera,
        "stera.data": mock_data,
        "stera.models": mock_models,
    }, mock_session, mock_blurrer, mock_report


@pytest.fixture
def mock_stera_sdk(tmp_path):
    """
    Pytest fixture: patches stera-sdk modules into sys.modules for the test.
    Also creates a fake valid MCAP file for the recording path.
    """
    mods, session, blurrer, report = _make_mock_stera_modules()

    # Create a valid MCAP file (magic bytes only)
    mcap_file = tmp_path / "test.mcap"
    mcap_file.write_bytes(MCAP_MAGIC + b"\x00" * 64)

    with patch.dict(sys.modules, mods):
        yield {
            "recording_path": str(mcap_file),
            "episodes_dir": str(tmp_path / "episodes"),
            "session": session,
            "blurrer": blurrer,
            "report": report,
        }


@pytest.mark.asyncio
async def test_run_pipeline_success(mock_stera_sdk, tmp_path):
    """
    Full pipeline run with all mocked SDK calls should return a PipelineResult.
    """
    from app.pipeline import run_pipeline

    log_lines = []

    result = await run_pipeline(
        recording_path=mock_stera_sdk["recording_path"],
        job_id="test-job-001",
        episodes_dir=mock_stera_sdk["episodes_dir"],
        emit=log_lines.append,
        include_hand_tracking=False,
    )

    # Result should be a PipelineResult
    assert isinstance(result, PipelineResult)
    assert result.episode_path.endswith("test-job-001")
    assert result.metadata["frame_count"] == 3
    assert result.metadata["has_depth"] is True
    assert result.metadata["has_pose"] is True

    # Log lines should include key milestones
    all_logs = "\n".join(log_lines)
    assert "[validate]" in all_logs
    assert "[inspect]" in all_logs
    assert "[blur]" in all_logs
    assert "[export]" in all_logs
    assert "[done]" in all_logs


@pytest.mark.asyncio
async def test_run_pipeline_missing_rgb_stream(mock_stera_sdk):
    """
    Recording without an RGB stream should raise PipelineError.
    """
    from app.pipeline import run_pipeline

    # Override stream_info to return no rgb stream
    mock_stera_sdk["session"].stream_info.return_value = {
        "depth": {"fps": 15},
        # No "rgb"
    }

    with pytest.raises(PipelineError) as exc_info:
        await run_pipeline(
            recording_path=mock_stera_sdk["recording_path"],
            job_id="test-job-002",
            episodes_dir=mock_stera_sdk["episodes_dir"],
            emit=lambda _: None,
        )

    assert "no rgb stream" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_run_pipeline_invalid_mcap(tmp_path, mock_stera_sdk):
    """
    A file that the SDK rejects (MCAPReader raises) should raise PipelineError.
    """
    from app.pipeline import run_pipeline

    # Make MCAPReader raise an exception to simulate a corrupt file
    import stera.data as stera_data
    stera_data.MCAPReader.side_effect = RuntimeError("corrupt MCAP footer")

    bad_file = tmp_path / "corrupt.mcap"
    bad_file.write_bytes(MCAP_MAGIC + b"\xff" * 64)  # Valid magic, corrupt body

    with pytest.raises(PipelineError) as exc_info:
        await run_pipeline(
            recording_path=str(bad_file),
            job_id="test-job-003",
            episodes_dir=mock_stera_sdk["episodes_dir"],
            emit=lambda _: None,
        )

    assert "cannot open recording" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_run_pipeline_hand_tracking_failure_is_nonfatal(mock_stera_sdk):
    """
    HandTracker failing to load should NOT raise — it should log a warning
    and continue without hand tracking.
    """
    from app.pipeline import run_pipeline

    import stera.models as stera_models
    stera_models.HandTracker.side_effect = RuntimeError("mediapipe model not found")

    log_lines = []

    result = await run_pipeline(
        recording_path=mock_stera_sdk["recording_path"],
        job_id="test-job-004",
        episodes_dir=mock_stera_sdk["episodes_dir"],
        emit=log_lines.append,
        include_hand_tracking=True,  # Opt into hand tracking
    )

    # Should still succeed
    assert isinstance(result, PipelineResult)

    # Warning about hand tracker failure should be in logs
    all_logs = "\n".join(log_lines)
    assert "WARNING" in all_logs or "warning" in all_logs.lower()
    assert "HandTracker" in all_logs or "hand" in all_logs.lower()


@pytest.mark.asyncio
async def test_run_pipeline_qc_failure_is_nonfatal(mock_stera_sdk):
    """
    QC report (Evaluate) failing should NOT raise — health_score should be None
    and report_path should be empty string.
    """
    from app.pipeline import run_pipeline

    import stera as stera_mod
    stera_mod.Evaluate.side_effect = RuntimeError("evaluate model not available")

    log_lines = []

    result = await run_pipeline(
        recording_path=mock_stera_sdk["recording_path"],
        job_id="test-job-005",
        episodes_dir=mock_stera_sdk["episodes_dir"],
        emit=log_lines.append,
    )

    # Should still succeed, but without health score or report
    assert isinstance(result, PipelineResult)
    assert result.health_score is None
    assert result.report_path == ""

    # Warning should appear in logs
    all_logs = "\n".join(log_lines)
    assert "WARNING" in all_logs or "warning" in all_logs.lower()


@pytest.mark.asyncio
async def test_run_pipeline_emits_progress_logs(mock_stera_sdk):
    """
    Pipeline should emit meaningful log lines at each step.
    """
    from app.pipeline import run_pipeline

    log_lines = []

    await run_pipeline(
        recording_path=mock_stera_sdk["recording_path"],
        job_id="test-job-006",
        episodes_dir=mock_stera_sdk["episodes_dir"],
        emit=log_lines.append,
    )

    prefixes_expected = ["[pipeline]", "[validate]", "[inspect]", "[blur]", "[export]", "[done]"]
    all_logs = "\n".join(log_lines)
    for prefix in prefixes_expected:
        assert prefix in all_logs, f"Expected log prefix '{prefix}' not found in output"
