# DECISIONS.md — Architecture Decision Record for Stera Episode Studio Backend

## ADR-001: In-Process asyncio.Queue Job Runner (not Celery)

**Decision:** Use an `asyncio.Queue` consumed by a single background task (`job_runner`)
instead of Celery + Redis/RabbitMQ.

**Rationale:**
- This is a single-user internal tool — there is no need for distributed workers,
  task routing, or multi-broker fanout.
- Celery would require running two extra services (broker + worker process) and adds
  significant operational complexity for zero user-facing benefit.
- `asyncio.Queue` is sufficient: one job at a time, same process, zero infra.
- Per-job `asyncio.Queue` for log lines enables SSE without any pub/sub layer.

**Trade-offs:**
- Jobs are lost on server restart (mitigation: `status='queued'` in DB allows recovery).
- No horizontal scaling (acceptable for the single-user use case).
- If a job is running when the server shuts down, it will be interrupted.

**If this changes:** Replace `enqueue_job()` with a Celery task and the per-job log
queue with Redis pub/sub. The pipeline and worker code are already decoupled enough
to support this migration with minimal changes.

---

## ADR-002: Firebase JWT Verification Without Admin SDK

**Decision:** Verify Firebase ID tokens by fetching Google's public X.509 certificates
and using `python-jose` for RS256 JWT verification, rather than using the
`firebase-admin` SDK.

**Rationale:**
- `firebase-admin` requires a service account JSON file, adding a credential management
  burden that is disproportionate for this use case.
- The Firebase public key endpoint is stable and well-documented.
- `python-jose` covers all required claim validation (iss, aud, exp, iat, sub).
- A 5-minute in-memory cache prevents hammering Google's endpoint on every request.

**Trade-offs:**
- Manual cache management vs Admin SDK's built-in key rotation handling.
- Must explicitly validate all claims (see `verify_firebase_token()`).

---

## ADR-003: Lazy Frame Processing (Generator Pattern)

**Decision:** Process MCAP frames one at a time using `session.frames()` generator,
never accumulating all frames in memory.

**Rationale:**
- A 1-hour session at 60fps = ~216,000 frames. At ~1MB per frame (RGB 1920×1080),
  that is ~216 GB of peak memory if all frames are loaded at once.
- The generator pattern keeps memory flat at ~1 frame at a time.
- The executor thread (`_process_frames_lazy`) runs this sync loop without blocking
  the asyncio event loop.

**Stream sync tolerance:**
- `max_depth_dt=0.1s`: LiDAR typically runs at 10–30 Hz; ±100ms finds the nearest
  depth frame for each RGB frame without overly strict rejection.
- `max_pose_dt=0.05s`: 6-DoF pose sensors are well-synced; 50ms is generous.
- These match the stera-sdk quickstart defaults, set explicitly here for documentation.

---

## ADR-004: Non-Fatal QC Report (Evaluate)

**Decision:** If `stera.Evaluate` raises an exception, log a warning and continue
without a health score or report. The episode export is still delivered.

**Rationale:**
- The primary output (blurred episode bundle) is more important than the QC report.
- QC model failures may be transient (network model download, GPU memory, etc.).
- Failing the entire job because of QC would discard a valid blurred episode.
- The frontend handles `health_score: null` and `report_path: ""` gracefully.

---

## ADR-005: MCAP Magic Byte Validation at Upload Time

**Decision:** Validate `.mcap` magic bytes before inserting any recording into the DB.

**Rationale:**
- Fails fast: users get immediate feedback instead of discovering bad files only when
  a job is queued and fails deep in the pipeline.
- Magic byte check is O(8 bytes) — essentially free compared to opening the SDK.
- The full `MCAPReader(check_format=True)` validation is still done inside the pipeline
  as a second layer of defence against corrupt-but-valid-magic files.

---

## ADR-006: Scan-on-List for Recordings Discovery

**Decision:** `GET /api/recordings` scans `RECORDINGS_DIR` on every call instead of
running a background file-watcher daemon.

**Rationale:**
- Avoids needing `watchdog` or inotify — one less background task.
- The recordings directory is managed externally (volume mount, SCP, etc.).
- For a single-user tool with a small directory (tens to hundreds of files),
  a `os.scandir()` on each list request has negligible latency.
- Upsert logic ensures idempotency — rescanning never creates duplicates.

**Trade-offs:**
- Not suitable for directories with thousands of files (use a file watcher then).
- Every list request touches the filesystem (mitigated by OS filesystem cache).

---

## ADR-007: Authenticated File Serving for Episode Content

**Decision:** All episode file endpoints (`/api/files/`) require Firebase authentication.
There are no public URLs for episode video or QC reports.

**Rationale:**
- Recordings contain people's faces (even blurred, they constitute PII).
- Direct file URLs (e.g. via nginx `sendfile`) would bypass auth controls.
- FastAPI `FileResponse` after the `get_current_user` dependency ensures auth is
  checked on every request before any file bytes are sent.

**Note:** In production with large video files, consider using `X-Accel-Redirect`
(nginx) or S3 presigned URLs with short TTLs instead of streaming through FastAPI,
while still performing the auth check in FastAPI before issuing the redirect.
