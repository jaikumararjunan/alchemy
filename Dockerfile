# ─────────────────────────────────────────────────────────────────────────────
# Alchemy Trading Platform — Multi-Stage Dockerfile
#
# Stage 1: frontend-builder   — Node 20 + npm build → /app/static
# Stage 2: api                — Python 3.12 slim + FastAPI + React static files
#
# Build:   docker build -t alchemy:local .
# Run:     docker run -p 8000:8000 alchemy:local
# ─────────────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Build React frontend
# ══════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy package files first for layer caching
COPY frontend/package*.json ./

# Install Node dependencies
RUN npm ci --silent

# Copy source and build
COPY frontend/ ./
RUN npm run build

# Output: /frontend/dist  (Vite default output dir)


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Python API + serve static files
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS api

LABEL maintainer="jai@akilamirthya.in"
LABEL org.opencontainers.image.title="Alchemy Trading Platform"
LABEL org.opencontainers.image.version="0.6.0"

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── App user (don't run as root) ─────────────────────────────────────────────
RUN useradd -r -s /bin/bash -d /app alchemy

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.docker.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install -r requirements.docker.txt --no-cache-dir

# ── Application code ──────────────────────────────────────────────────────────
COPY alchemy/ ./alchemy/
COPY config/  ./config/
COPY pyproject.toml .

# Install the package itself
RUN pip install -e . --no-deps --no-cache-dir

# ── Copy built frontend from stage 1 → serve as static files ─────────────────
# FastAPI mounts /app/static at "/" in production
COPY --from=frontend-builder /frontend/dist ./static/

# ── Data directory (SQLite DB, ChromaDB, logs) ────────────────────────────────
RUN mkdir -p /app/data/logs /app/data/chromadb /app/.alchemy/vault && \
    chown -R alchemy:alchemy /app

# ── Switch to non-root user ───────────────────────────────────────────────────
USER alchemy

# ── Port ─────────────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Start ─────────────────────────────────────────────────────────────────────
CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]
