# Stera Episode Studio

> Internal tool for processing egocentric MCAP recordings through the Stera pipeline.

## Architecture

```
frontend/  (React + Vite + TypeScript + Tailwind)  →  Vercel
backend/   (FastAPI + Python + stera-sdk)           →  Render
database   (PostgreSQL)                             →  Neon
auth       (Firebase Auth)                          →  Firebase
```

## Cold-Clone Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- ffmpeg on PATH (required by stera-sdk for export)
- Docker + Docker Compose (recommended path)

### 1. Clone & configure

```bash
git clone <repo-url>
cd stera-episode-studio
```

### 2. Backend environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env:
#   DATABASE_URL        = your Neon postgres connection string (asyncpg format)
#   RECORDINGS_DIR      = absolute path to the folder with .mcap files
#   EPISODES_DIR        = absolute path for output episodes
#   FIREBASE_PROJECT_ID = your Firebase project ID
```

### 3. Frontend environment

```bash
cp frontend/.env.example frontend/.env
# Edit frontend/.env with your Firebase web app config
# VITE_API_URL = http://localhost:8000 (for local dev)
```

### 4a. Run with Docker (recommended — matches cold-clone behavior)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

### 4b. Run manually

**Backend:**
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### 5. Add recordings

Drop `.mcap` files into the directory you set as `RECORDINGS_DIR`. Then click **Refresh** in the UI — the backend scans the directory, validates MCAP magic bytes, and lists them.

## How to use

1. Open http://localhost:5173
2. Click **Start a Project** to go to the recordings list
3. Select a recording → click **Process Recording**
4. Watch live progress in the terminal log
5. View results: exported video, health score, and interactive QC report

## Running tests

```bash
cd backend
pytest -v
```

## Deployment

### Backend → Render

1. Create a new Web Service in Render
2. Set root directory to `backend/`
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables from `backend/.env`
6. Mount a persistent disk at `/data` for recordings and episodes

### Frontend → Vercel

1. Import the repo in Vercel
2. Set root directory to `frontend/`
3. Add environment variables from `frontend/.env`
4. Set `VITE_API_URL` to your Render backend URL

### Database → Neon

1. Create a Neon project at https://neon.tech
2. Copy the connection string in asyncpg format:
   `postgresql+asyncpg://user:pass@host/dbname`
3. Set as `DATABASE_URL` in backend `.env`
4. Tables are created automatically on first startup (`init_db()`)

## Project structure

```
stera-episode-studio/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS, lifespan
│   │   ├── config.py        # Settings (env vars)
│   │   ├── database.py      # Async SQLAlchemy + Neon
│   │   ├── models.py        # ORM: Recording, Job, Result
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── auth.py          # Firebase JWT verification
│   │   ├── pipeline.py      # stera-sdk wrapper
│   │   ├── worker.py        # asyncio job queue
│   │   └── routers/         # API route handlers
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/           # Hero, Capabilities, RecordingList, JobView, ResultView
│   │   ├── components/      # FadingVideo, BlurText, Navbar, icons
│   │   ├── api.ts           # Typed API client
│   │   └── firebase.ts      # Firebase auth
│   └── vercel.json
├── DECISIONS.md
├── KNOWN_ISSUES.md
└── docker-compose.yml
```
