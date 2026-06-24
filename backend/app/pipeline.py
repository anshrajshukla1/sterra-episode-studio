"""
app/pipeline.py — Stera SDK processing pipeline wrapper.

Design decisions:
- Frames processed lazily (generator) — never load all into memory.
  Sessions can be >1hr at full frame rate; loading all frames would OOM.
- FaceBlurrer runs on every RGB frame — non-negotiable (PII requirement).
- HandTracker is optional — included but can be disabled via config.
  MediaPipe hand model may not install cleanly in all environments.
- MCAPReader run with check_format=True — fail loud on malformed input.
  We want immediate rejection of bad files rather than silent corruption.
- Each step emits progress via the emit() callback (consumed by SSE).
- All stera-sdk calls are run in a thread pool executor so they never
  block the asyncio event loop (SDK is synchronous).
- Exceptions from individual hand-tracking frames are non-fatal and
  silently skipped — hand tracking loss on one frame is acceptable.
- QC report (Evaluate) failure is non-fatal — we still deliver the episode.
- Sync frame-processing loop in _process_frames_lazy to avoid executor
  overhead per frame (would be enormous for 60fps × 3600s = 216k frames).

See DECISIONS.md for architecture rationale.
"""
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Structured output from a successful pipeline run."""
    episode_path: str
    report_path: str
    health_score: float | None
    metadata: dict = field(default_factory=dict)
    # metadata keys: duration_s, frame_count, stream_names, has_depth, has_pose


# ── Error type ────────────────────────────────────────────────────────────────

class PipelineError(Exception):
    """
    Raised when the pipeline encounters a known-bad input or SDK error.

    Callers can catch PipelineError to surface a user-friendly message
    without needing to understand internal SDK exception types.
    """
    pass


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_pipeline(
    recording_path: str,
    job_id: str,
    episodes_dir: str,
    emit: Callable[[str], None],
    include_hand_tracking: bool = False,
) -> PipelineResult:
    """
    Run the full Stera processing pipeline on an MCAP recording.

    Steps:
      1. Validate MCAP format (MCAPReader with check_format=True)
      2. Inspect available streams (rgb, depth, pose, frame_count, duration_s)
      3. Load FaceBlurrer — required, never skipped
      4. Load HandTracker — optional, failures are non-fatal
      5. Process frames lazily — blur every RGB frame, optionally track hands
      6. Export episode bundle to episodes_dir/job_id/
      7. Generate QC report (Evaluate) — non-fatal if this step fails
      8. Return PipelineResult with paths + metadata

    All blocking SDK calls are dispatched to asyncio's default thread pool
    via loop.run_in_executor(None, ...) so the event loop stays unblocked.

    Args:
        recording_path:       Absolute path to the .mcap file.
        job_id:               UUID string for this job (used as output dir name).
        episodes_dir:         Root directory for episode exports.
        emit:                 Sync callback — each call writes one log line to SSE.
        include_hand_tracking: If True, attempt to run HandTracker on each frame.

    Returns:
        PipelineResult with episode_path, report_path, health_score, metadata.

    Raises:
        PipelineError: Known bad input or SDK failure with descriptive message.
        Exception:     Unexpected errors — propagated without modification.
    """
    loop = asyncio.get_event_loop()

    emit(f"[pipeline] Starting pipeline for job {job_id}")
    emit(f"[pipeline] Recording: {recording_path}")

    # ── Step 1: Validate MCAP format ─────────────────────────────────────────
    emit("[validate] Opening recording with format check…")
    try:
        session = await loop.run_in_executor(
            None,
            lambda: _open_session(recording_path),
        )
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"Cannot open recording '{recording_path}': {exc}") from exc

    emit("[validate] Recording opened successfully.")

    # ── Step 2: Inspect streams ───────────────────────────────────────────────
    emit("[inspect] Reading stream metadata…")
    try:
        streams = await loop.run_in_executor(
            None,
            lambda: _inspect_streams(session),
        )
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"Failed to inspect streams: {exc}") from exc

    emit(f"[inspect] Streams found: {', '.join(str(k) for k in streams.keys()) or 'none'}")
    emit(f"[inspect] Has depth: {'depth' in streams}")
    emit(f"[inspect] Has pose:  {'pose' in streams}")

    if "rgb" not in streams:
        raise PipelineError(
            "Recording has no RGB stream — cannot process. "
            "Face blur requires RGB frames. "
            f"Found streams: {list(streams.keys())}"
        )

    frame_count: int = int(streams.get("frame_count", 0))
    duration_s: float = float(streams.get("duration_s", 0.0))
    emit(f"[inspect] Estimated frames: {frame_count}, duration: {duration_s:.1f}s")

    # ── Step 3: Load FaceBlurrer — REQUIRED ──────────────────────────────────
    emit("[blur] Initializing FaceBlurrer (mediapipe)…")
    try:
        blurrer = await loop.run_in_executor(
            None,
            lambda: _load_blurrer(),
        )
    except Exception as exc:
        raise PipelineError(
            f"Failed to load FaceBlurrer: {exc}. "
            "Check that mediapipe is installed correctly."
        ) from exc

    emit("[blur] FaceBlurrer ready.")

    # ── Step 4: Load HandTracker — OPTIONAL ──────────────────────────────────
    hand_tracker = None
    if include_hand_tracking:
        emit("[hands] Initializing HandTracker (mediapipe)…")
        try:
            hand_tracker = await loop.run_in_executor(
                None,
                lambda: _load_hand_tracker(),
            )
            emit("[hands] HandTracker ready.")
        except Exception as exc:
            # Non-fatal: hand tracking is opt-in and model may not be installed
            emit(
                f"[hands] WARNING: HandTracker failed to load ({exc}). "
                "Skipping hand tracking for this job."
            )
            hand_tracker = None

    # ── Step 5: Process frames lazily ────────────────────────────────────────
    emit("[process] Processing frames (lazy generator — no full-load into memory)…")
    try:
        processed = await loop.run_in_executor(
            None,
            lambda: _process_frames_lazy(
                session, blurrer, hand_tracker, frame_count, emit
            ),
        )
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"Frame processing failed: {exc}") from exc

    emit(f"[process] Processed {processed} frames total.")

    # ── Step 6: Export episode ────────────────────────────────────────────────
    episode_path = os.path.join(episodes_dir, job_id)
    os.makedirs(episode_path, exist_ok=True)
    emit(f"[export] Exporting episode to {episode_path}…")
    try:
        await loop.run_in_executor(
            None,
            lambda: session.export(episode_path),
        )
    except Exception as exc:
        raise PipelineError(f"Export failed: {exc}") from exc

    emit("[export] Export complete.")

    # ── Step 7: Generate QC report — NON-FATAL ────────────────────────────────
    report_path: str | None = None
    health_score: float | None = None
    emit("[evaluate] Generating QC report…")
    try:
        from stera import Evaluate  # noqa: PLC0415 — deferred to avoid import side-effects

        report = await loop.run_in_executor(
            None,
            lambda: Evaluate(session),
        )

        # health_score may be a property or a callable — handle both
        raw_score = getattr(report, "health_score", None)
        if callable(raw_score):
            health_score = raw_score()
        else:
            health_score = raw_score

        candidate_report_path = os.path.join(episode_path, "report.html")
        await loop.run_in_executor(
            None,
            lambda: report.save(candidate_report_path),
        )
        report_path = candidate_report_path
        emit(f"[evaluate] QC report saved. Health score: {health_score}")

    except Exception as exc:
        # QC report failure is explicitly non-fatal per spec.
        # We already have the exported episode — surfacing the error is enough.
        emit(
            f"[evaluate] WARNING: QC report generation failed: {exc}. "
            "Continuing without QC report."
        )
        logger.warning("QC report generation failed for job %s: %s", job_id, exc)

    emit("[done] Pipeline complete.")

    return PipelineResult(
        episode_path=episode_path,
        report_path=report_path or "",
        health_score=health_score,
        metadata={
            "duration_s": duration_s,
            "frame_count": processed,
            "stream_names": [k for k in streams.keys() if k not in ("frame_count", "duration_s")],
            "has_depth": "depth" in streams,
            "has_pose": "pose" in streams,
        },
    )


# ── Sync SDK helpers (called via run_in_executor) ─────────────────────────────

def _open_session(recording_path: str):
    """
    Open an MCAP recording using the Stera SDK.

    check_format=True causes the SDK to validate the MCAP structure before
    returning — any malformed file raises an exception immediately rather
    than failing mid-processing.  This is intentional: fail loud, fail early.
    """
    from stera.data import MCAPReader  # noqa: PLC0415

    return MCAPReader(recording_path, check_format=True)


def _inspect_streams(session) -> dict:
    """
    Return a dict of stream info plus frame_count and duration_s keys.

    Attempts to call the modern stream_info() API and falls back gracefully
    for older SDK versions that may not expose it.
    """
    info: dict = {}

    # Modern SDK: stream_info() returns a dict keyed by stream name
    try:
        stream_info = session.stream_info()
        if isinstance(stream_info, dict):
            info.update(stream_info)
    except AttributeError:
        # Older SDK — stream names may be exposed differently; skip gracefully
        logger.debug("session.stream_info() not available — using legacy fallback")

    # Frame count
    try:
        info["frame_count"] = int(session.frame_count())
    except AttributeError:
        info["frame_count"] = 0

    # Duration in seconds
    try:
        info["duration_s"] = float(session.duration())
    except AttributeError:
        info["duration_s"] = 0.0

    return info


def _load_blurrer():
    """Instantiate the FaceBlurrer model. Mediapipe model download may occur here."""
    from stera.models import FaceBlurrer  # noqa: PLC0415

    return FaceBlurrer(model="mediapipe")


def _load_hand_tracker():
    """Instantiate the HandTracker model. May fail if model weights not installed."""
    from stera.models import HandTracker  # noqa: PLC0415

    return HandTracker(model="mediapipe")


def _process_frames_lazy(
    session,
    blurrer,
    hand_tracker,
    total_frames: int,
    emit: Callable[[str], None],
) -> int:
    """
    Iterate over frames one at a time and process in-place.

    Memory design:
    - session.frames() is a generator — only one frame lives in memory at once.
    - clean_frame replaces the raw frame reference before next iteration.
    - For a 1-hour 60fps session (~216k frames) this keeps memory flat
      rather than accumulating all decoded frames.

    Sync tolerance parameters:
    - max_depth_dt=0.1s: LiDAR typically runs at 10–30 Hz, so ±100ms is
      necessary to find the nearest depth frame for each RGB frame.
    - max_pose_dt=0.05s: 6-DoF pose should be well-synced; 50ms is generous.
    - These values match the stera-sdk quickstart defaults, set explicitly
      here to document the choice rather than relying on hidden defaults.

    Args:
        session:       Open MCAPReader session.
        blurrer:       Loaded FaceBlurrer instance.
        hand_tracker:  Loaded HandTracker instance, or None.
        total_frames:  Estimated total frames (used for progress percent).
        emit:          Sync log-line callback (writes to SSE queue).

    Returns:
        Number of frames successfully processed.

    Raises:
        PipelineError: If the frame generator raises a non-recoverable exception.
    """
    processed = 0
    last_emit_at = time.monotonic()

    try:
        for frame in session.frames(max_depth_dt=0.1, max_pose_dt=0.05):
            # ── Face blur — mandatory on every RGB frame ──────────────────────
            clean_frame = blurrer.blur(frame)
            session.add_rgb_frame(frame.index, clean_frame)

            # ── Hand tracking — optional, per-frame failures are non-fatal ───
            if hand_tracker is not None:
                try:
                    poses = hand_tracker.detect_hands(frame)
                    session.add_hand_pose(frame.index, poses)
                except Exception as hand_exc:  # noqa: BLE001
                    # A single frame's hand detection failure is acceptable.
                    # Logging at DEBUG level — would be very noisy at INFO.
                    logger.debug(
                        "Hand tracking failed on frame %s: %s",
                        frame.index,
                        hand_exc,
                    )

            processed += 1

            # ── Progress reporting (rate-limited to avoid SSE flooding) ───────
            now = time.monotonic()
            if now - last_emit_at >= 2.0:
                pct = int(100 * processed / total_frames) if total_frames > 0 else 0
                emit(f"[process] Frame {processed}/{total_frames} ({pct}%)")
                last_emit_at = now

    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(
            f"Frame iteration failed at frame {processed}: {exc}"
        ) from exc

    return processed


# ── Standalone validation helper ──────────────────────────────────────────────

def validate_mcap_file(filepath: str) -> tuple[bool, str]:
    """
    Quickly validate an MCAP file by checking its magic bytes.

    The MCAP format specification defines the magic bytes as:
      0x89 0x4D 0x43 0x41 0x50 0x30 0x0D 0x0A  (i.e. b'\\x89MCAP0\\r\\n')

    This check is intentionally lightweight — it runs before inserting the
    recording into the DB so we reject obviously bad files immediately,
    without spinning up the full SDK reader.

    Args:
        filepath: Absolute path to the candidate .mcap file.

    Returns:
        (True, "")               — file appears to be a valid MCAP recording.
        (False, error_message)   — file is invalid; error_message explains why.
    """
    MCAP_MAGIC = b"\x89MCAP0\r\n"

    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
    except OSError as exc:
        return False, f"Cannot read file '{filepath}': {exc}"

    if len(header) < 8:
        return False, (
            f"File too small ({len(header)} bytes) to be a valid MCAP recording"
        )

    if header[:8] != MCAP_MAGIC:
        return False, (
            f"Not a valid MCAP file — magic bytes mismatch. "
            f"Expected {MCAP_MAGIC.hex()}, got {header[:8].hex()}"
        )

    return True, ""
