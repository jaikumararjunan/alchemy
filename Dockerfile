# ════════════════════════════════════════════════════════════════
#  Alchemy — Production Docker Image
#  Stage 1: Build React frontend  (node:20-alpine)
#  Stage 2: Run FastAPI backend   (python:3.12-slim)
# ════════════════════════════════════════════════════════════════

# ── Stage 1: Frontend builder ─────────────────────────────────────
FROM node:20-alpine AS frontend-builder

# Security: run as non-root
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app/frontend
RUN chown appuser:appgroup /app/frontend
USER appuser

# Install deps with package.json (lock file optional — npm install handles both)
COPY --chown=appuser:appgroup frontend/package.json ./
COPY --chown=appuser:appgroup frontend/package-lock.json* ./

RUN npm install --prefer-offline --legacy-peer-deps 2>&1 | tail -3

# Build production bundle
COPY --chown=appuser:appgroup frontend/ ./
RUN npm run build && ls -la dist/ && test -f dist/index.html

# ── Stage 2: Python backend ───────────────────────────────────────
FROM python:3.12-slim AS app

LABEL maintainer="Alchemy Trading Platform"
LABEL description="AI-Powered Algorithmic Trading Platform"
LABEL version="0.6"

WORKDIR /app

# System security: minimal packages, no cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libffi-dev libssl-dev curl ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Upgrade pip to latest for best resolver
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Python deps — use requirements with resolved compatible versions
COPY requirements.local.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip check \
    && echo "✓ All dependencies installed and verified"

# Application source
COPY alchemy/  ./alchemy/
COPY scripts/  ./scripts/

# Frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./static

# Verify app can be imported before building image
RUN python3 -c "from alchemy.api.app import app; print(f'✓ App loaded OK — {len(app.routes)} routes')"

# Data directory for SQLite
RUN mkdir -p /data && chmod 700 /data

# Security: non-root user, minimal permissions
RUN groupadd -r alchemy && useradd -r -g alchemy -d /app -s /sbin/nologin alchemy \
    && chown -R alchemy:alchemy /app /data
USER alchemy

# Security: read-only filesystem hints
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "alchemy.api.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--forwarded-allow-ips", "*", \
     "--proxy-headers"]
