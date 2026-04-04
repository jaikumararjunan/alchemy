# ════════════════════════════════════════════════════════════════
#  Alchemy — Production Docker Image  v0.6
# ════════════════════════════════════════════════════════════════

# ── Stage 1: Frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
COPY frontend/package-lock.json* ./
RUN npm install --prefer-offline --legacy-peer-deps 2>&1 | tail -3
COPY frontend/ ./
RUN npm run build && test -f dist/index.html && echo "Frontend OK"

# ── Stage 2: Backend ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libffi-dev libssl-dev curl ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.local.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip check

COPY alchemy/  ./alchemy/
COPY scripts/  ./scripts/
COPY --from=frontend-builder /app/frontend/dist ./static

# Create data dir as root with wide-open permissions BEFORE switching user
# This ensures the mounted volume is always writable by the app user
RUN mkdir -p /data && chmod 777 /data && \
    useradd -r -u 1000 -g root -d /app -s /sbin/nologin alchemy && \
    chown -R alchemy:root /app && \
    chmod -R g+rw /app

USER alchemy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info", \
     "--forwarded-allow-ips", "*", "--proxy-headers"]
