# Stera Episode Studio

A full-stack, asynchronous web application for processing, analyzing, and reviewing raw `.mcap` robotics session recordings.

## Features
- **Dynamic Background Processing:** Asynchronous job runner implemented in Python using `asyncio` queues, allowing long-running MediaPipe face-blurring models to execute without blocking the main event loop.
- **Live Streaming Logs:** Real-time terminal log streaming to the frontend using Server-Sent Events (SSE).
- **Automated Directory Scanning:** The backend automatically watches and indexes any `.mcap` files placed in the data directory.
- **Firebase Authentication:** Secure Google Sign-in flow with pure-Python JWT cryptographic signature verification on the backend (zero reliance on the heavy Firebase Admin SDK).
- **Responsive "Liquid Glass" UI:** A custom, premium React frontend built with TailwindCSS and Framer Motion, featuring smooth micro-animations.

## Architecture
### Backend (FastAPI)
- **Framework:** FastAPI (Python 3.11)
- **Database:** Neon PostgreSQL (using `asyncpg` + async SQLAlchemy) or fallback to local SQLite (`aiosqlite`)
- **Processing:** `stera-sdk` wrapper implementing a streaming, non-memory-blocking video processing pipeline.
- **Auth:** `python-jose` for verifying Firebase ID tokens directly against Google's public X.509 certificates.

### Frontend (React + Vite)
- **Framework:** React 18 (TypeScript) with Vite
- **Styling:** Vanilla CSS + TailwindCSS (Dark Mode / Glassmorphism)
- **Routing:** React Router v6
- **Animations:** Framer Motion

## Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

## Setup & Installation

### 1. Configure Firebase Authentication
This application requires real Firebase Authentication keys to run. Please create a `.env` file in the **root of the project** (alongside `docker-compose.yml`) and add the Firebase configuration keys provided by the developer:

```env
VITE_FIREBASE_API_KEY="<insert_key_here>"
VITE_FIREBASE_AUTH_DOMAIN="<insert_domain_here>"
VITE_FIREBASE_PROJECT_ID="<insert_project_id_here>"
VITE_FIREBASE_STORAGE_BUCKET="<insert_bucket_here>"
VITE_FIREBASE_MESSAGING_SENDER_ID="<insert_sender_id_here>"
VITE_FIREBASE_APP_ID="<insert_app_id_here>"
```

### 2. Add Test Recordings
To test the pipeline, you can use your own `.mcap` files! Simply copy your files into the `backend/data/recordings` directory. The backend will automatically detect them.

### 3. Run the Application
Start the entire stack using Docker Compose:

```bash
docker-compose up --build
```

- **Frontend UI:** [http://localhost:5173](http://localhost:5173)
- **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

*(Note: The first build may take a few minutes as it installs ffmpeg and the necessary Python machine learning dependencies).*

## Pipeline Workflow
1. Navigate to the frontend and sign in using Google Auth.
2. The dashboard will list all recordings found in `backend/data/recordings`.
3. Click **Process Recording** to initiate the pipeline. You will be taken to a live terminal view.
4. Watch the logs stream in real-time as the backend unpacks the streams, runs MediaPipe Face Detection to blur PII on every RGB frame, and exports the final `rgb.mp4` video.
5. Once complete, click **View Results** to see the final QC report, health score, and processed video player.
