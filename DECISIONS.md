# DECISIONS.md — Architecture Journal

> Every non-obvious decision, the alternative rejected, and why.
> This document is weighted as heavily as the code (per §6 of the assignment spec).

---

## Architecture

### Why FastAPI (Python) instead of Node/Express?

The `stera-sdk` is Python-only. A Node backend would need to call Python as a subprocess — fragile, hard to debug, and indefensible in a live session. FastAPI gives us:
- Direct SDK import (no subprocess overhead or error propagation hell)
- Native `async/await` for non-blocking SSE streaming
- Pydantic models for schema validation (same ecosystem as SQLAlchemy 2.x)
- Excellent docs auto-generation (Swagger UI at `/docs`)

Alternative rejected: Node.js + Express spawning Python subprocess. Rejected because subprocess error handling is brittle and you can't stream progress easily across process boundaries without additional IPC plumbing.

### Why SSE instead of WebSockets for job progress?

Job progress is strictly one-directional: server → client. WebSockets are bidirectional — correct tool for chat, wrong tool here. SSE advantages:
- Simpler implementation (no upgrade handshake, no `ws://` protocol)
- Works through Vercel's edge network without extra config
- Auto-reconnects on connection drop (native browser behavior)
- Standard HTTP — no proxy issues

Alternative rejected: WebSockets. Rejected because complexity without benefit for unidirectional streaming.

### Why asyncio.Queue (in-process) instead of Celery?

This is a single-user internal tool for a robotics research team — not a multi-tenant SaaS. A Celery setup requires:
- A message broker (Redis or RabbitMQ)
- A separate worker process/container
- Additional infrastructure cost and cold-clone complexity

An in-process `asyncio.Queue` runs in the same FastAPI process, persists across a request cycle, and requires zero extra infrastructure. It's the right-sized solution.

Trade-off documented in KNOWN_ISSUES.md: if the server crashes mid-job, the queued/running jobs are lost (not persisted across restarts). For a production multi-user system, Celery + Redis would be the correct upgrade path.

### Why configured-directory scan instead of file upload?

The assignment states recordings can be over 1 hour at full frame rate. Uploading multi-hundred-MB binary files through a browser has sharp edges:
- Chunked upload handling for large files
- Resumable upload state (what happens if upload drops at 80%?)
- Validating a half-copied file is actually complete
- Browser memory pressure on large file selection

A configured directory (`RECORDINGS_DIR` env var) sidesteps all of this. The backend scans on request, validates MCAP magic bytes before listing, and rejects invalid files with a clear error. The researcher drops files in via their normal file system workflow (already how they work).

Decision recorded per §5.5 ("Getting files into the app is not free").

---

## §5 Judgment Tasks — Specific Answers

### §5.1 — Not every recording is well-formed

**Decision:** Use `MCAPReader(check_format=True)` which raises an explicit exception on malformed input. The exception message is surfaced to the UI via the SSE log stream and stored in `jobs.error_msg`. The job status is set to `'failed'` and the recording status to `'error'`.

**What we do NOT do:** Silent `try/except: pass`. Every error is logged with full traceback server-side and a human-readable message client-side.

For recordings with misaligned timestamps: `session.frames()` accepts `max_depth_dt` and `max_pose_dt` parameters. We set these explicitly to `0.1s` and `0.05s` respectively (matching the SDK quickstart). If a recording has no depth stream, `has_depth` is flagged as false in the result metadata and the UI surfaces this.

For recordings with missing streams: if there's no RGB stream, we reject the recording immediately with `PipelineError("Recording has no RGB stream — cannot process (face blur requires RGB frames)")`. If depth or pose is missing, we proceed but flag it.

**Fail loud vs. degrade gracefully:** We fail loud on malformed MCAP (bad magic bytes, corrupt format) because there's nothing useful we can do. We degrade gracefully on missing optional streams (depth, pose) because the core pipeline (RGB + face blur) can still run.

### §5.2 — At least one recording is large

**Decision:** Frames are processed lazily using `session.frames()` as a Python generator. We never accumulate all frames in memory — each frame is processed, added to the session, and the reference can be garbage collected. Progress is emitted via SSE every 2 seconds (not every frame — SSE has overhead).

We specifically did NOT write code that collects `list(session.frames())` or similar patterns that would load everything into memory.

### §5.3 — Faces are PII

**Decision:** This is a correctness requirement, not a nice-to-have.

1. `FaceBlurrer` runs on EVERY RGB frame before any export. The blurring step is before `session.export()` — no unblurred frame is ever written to disk in the episode directory.
2. Episode files are served exclusively via `/api/files/{job_id}/video` and `/api/files/{job_id}/report` — both require a valid Firebase ID token.
3. There are no public URLs for episode content. The frontend passes the token as a query parameter for video/iframe loading (browsers can't set Authorization headers on `<video src>` or `<iframe src>`).
4. The recordings directory itself (raw `.mcap` files) is never served — only processed, blurred output.

### §5.4 — The SDK will surprise you

**Decision:** We wrap SDK calls in specific try/except blocks with meaningful error messages. We never use bare `except: pass`. Every SDK call that fails:
- Gets logged with the actual exception type and message
- Is stored in `jobs.error_msg`
- Is surfaced to the user via SSE as `[error] ...`
- Causes the job to be marked `'failed'` (not silently retried)

For the `HandTracker`: we attempted to load it, caught any `ImportError` or SDK exception, logged it as a warning, and continued without hand tracking. This is explicitly documented as a non-fatal degradation (hand tracking is optional per spec).

### §5.5 — Getting files into the app is not free

**Decision:** See "Why configured-directory scan" above.

Additional validation: before a `.mcap` file is added to the database, we check its magic bytes (`\x89MCAP0\r\n` at offset 0). A file that fails this check is logged with the actual bytes we found, and excluded from the listing with an appropriate error message. This catches junk files, truncated downloads, and renamed non-MCAP files.

---

## Database Design

### Why Neon PostgreSQL instead of SQLite?

SQLite has no async driver and requires WAL mode for concurrent reads. Neon PostgreSQL works well with `asyncpg` + SQLAlchemy 2.x async mode, and the free tier is sufficient for this use case. Cold-clone reproducibility is better with a hosted DB (no local setup needed).

### Why separate Recording, Job, Result tables?

One recording can have multiple job attempts (if a job fails, you may want to retry). The result is logically separate from the job — it exists only if the job succeeded. This normalized schema avoids the alternative: a single fat table with nullable columns for both job state and result data.

---

## Auth

### Why Firebase Auth instead of AWS Cognito?

Both are viable. Firebase Auth was chosen because:
- Simpler SDK (fewer IAM policies to set up)
- Free tier: 10k MAUs (more than sufficient for an internal tool)
- ID tokens are standard JWTs — verifiable without the Firebase Admin SDK using JWKS

The backend verifies Firebase ID tokens using the public JWKS endpoint (`https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com`). Keys are cached in memory for 5 minutes (they rotate daily).

---

## Stretch Goal Selection

**Chosen: Multi-recording dashboard** (health scores across all sessions, sortable)
- Pure UI + DB query addition — no new infra risk
- Shows system design maturity

**Not chosen: Cancellation/resumability**
- Would require either persisted worker state or a real task queue (Celery + Redis)
- Adding that infra while the core is fresh violates the spec's explicit warning: "If you spend time on stretch goals while the core is shaky, that counts against you."

**Not chosen: Live 3D viewer**
- Requires Three.js integration + point cloud parsing
- High risk, low certainty of working on all provided data formats

**Not chosen: Re-run with different parameters**
- Interesting but requires parameter UI design decisions that could bloat scope

---

## What I'd Do With Another Day

1. **Persistent job queue**: Migrate from asyncio.Queue to Celery + Redis so jobs survive server restarts
2. **Job cancellation**: `asyncio.Task` cancellation + cleanup of partial episode directories
3. **Streaming video with Range headers**: The current FileResponse serves full files. For large exported videos, byte-range requests would allow seeking without downloading the whole file
4. **3D point cloud viewer**: Three.js with the exported mesh/map data (if present in the recording)
5. **Multi-user support**: Right now RECORDINGS_DIR is global. A multi-user system would need per-user recording namespacing

---

## What I Knowingly Cut

1. **Email/password UI for login**: Auth is wired but there's no login page in the UI — you need to use the Firebase console or a pre-provisioned token. This is acceptable for an internal tool where users are provisioned by an admin.
2. **Pagination on recordings list**: The scan-and-list approach works fine for dozens of recordings. For thousands, we'd need server-side pagination.
3. **Upload UI**: Deliberately cut — see §5.5 decision above.
