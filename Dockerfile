# ════════════════════════════════════════════════════════════════
#  Alchemy — Multi-stage Docker build
#  Stage 1: Build React frontend (Node 20)
#  Stage 2: Run FastAPI backend (Python 3.12)
# ════════════════════════════════════════════════════════════════

# ── Stage 1: Frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy package files first for layer caching
COPY frontend/package.json ./
COPY frontend/package-lock.json* ./

# Install deps — use npm install as fallback if lock file missing/mismatched
RUN npm install --legacy-peer-deps

# Copy source and build
COPY frontend/ ./
RUN npm run build

# Verify build succeeded
RUN test -d dist && test -f dist/index.html \
    || (echo "ERROR: frontend build failed — dist/ missing" && exit 1)

# ── Stage 2: Backend ──────────────────────────────────────────────
FROM python:3.12-slim AS app
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.local.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application source
COPY alchemy/ ./alchemy/
COPY scripts/  ./scripts/

# Frontend dist from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./static

# Data directory (SQLite lives here)
RUN mkdir -p /data && chmod 777 /data

# Non-root user for security
RUN useradd -m -u 1000 alchemy \
    && chown -R alchemy:alchemy /app
USER alchemy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
