# ════════════════════════════════════════════════════════════════
#  Alchemy — Multi-stage Docker build
#  Stage 1: Build React frontend  (node:20-alpine)
#  Stage 2: Run FastAPI backend   (python:3.12-slim)
# ════════════════════════════════════════════════════════════════

# ── Stage 1: Frontend build ───────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy package files (lock file optional)
COPY frontend/package.json ./
COPY frontend/package-lock.json* ./

# Install with fallback if lock file missing/mismatched
RUN npm install --prefer-offline --legacy-peer-deps 2>&1 | tail -5

# Build production bundle
COPY frontend/ ./
RUN npm run build

# Verify build
RUN ls -la dist/ && test -f dist/index.html

# ── Stage 2: Python backend ───────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System deps (consolidated in one layer)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libffi-dev libssl-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first to latest
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install Python dependencies
# Copy requirements first for Docker layer caching
COPY requirements.local.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application source code
COPY alchemy/ ./alchemy/
COPY scripts/  ./scripts/

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./static

# Data directory for SQLite database
RUN mkdir -p /data && chmod 777 /data

# Security: run as non-root user
RUN useradd -m -u 1000 alchemy \
    && chown -R alchemy:alchemy /app /data
USER alchemy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--forwarded-allow-ips", "*"]
