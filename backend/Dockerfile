# ── Stera Episode Studio — Backend Dockerfile ──────────────────────────────
# Base: slim Python 3.11 — keeps image small while maintaining compatibility
FROM python:3.11-slim

# Install system dependencies:
# - ffmpeg: required by stera-sdk for video encoding/decoding
# - libgl1: OpenCV dependency needed by mediapipe (face blur model)
# - gcc / build-essential: needed to compile asyncpg C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgles2 \
    libegl1 \
    libsm6 \
    libxext6 \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set workdir early so all relative paths resolve correctly
WORKDIR /app

# Copy and install Python deps first (layer cache friendly — only re-runs on
# requirements change, not on every code change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create data directories used by the app (overridden by volume mounts in prod)
RUN mkdir -p /data/recordings /data/episodes

# Expose the application port
EXPOSE 8000

# Run the FastAPI app via uvicorn with:
# --host 0.0.0.0 — listen on all interfaces (required inside Docker)
# --port 8000    — match EXPOSE above
# Production deployments should add --workers N for multi-process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
