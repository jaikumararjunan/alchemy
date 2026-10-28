#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE"

if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "alchemy backend already healthy on :8000"
  exit 0
fi

if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:////${WORKSPACE}/data/alchemy.db}"
export ENV="${ENV:-development}"

# shellcheck disable=SC1091
source .venv/bin/activate
exec python -m uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000
