# ── Stage 1: Frontend builder ────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Production app ──────────────────────────────────────
FROM python:3.12-slim AS app
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.local.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY alchemy/      ./alchemy/
COPY scripts/      ./scripts/

# Frontend dist from builder
COPY --from=frontend-builder /app/frontend/dist ./static

# Data directory
RUN mkdir -p /data && chmod 777 /data

# Non-root user
RUN useradd -m -u 1000 alchemy && chown -R alchemy:alchemy /app
USER alchemy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
