# Testing Alchemy Backend API

## Overview
Alchemy is a FastAPI trading platform with SQLite (dev) / PostgreSQL (prod). The backend entry point is `alchemy.api.app:app`.

## Local Backend Setup

### Start the server
All dev credentials are in `.env.local` at the repo root. Source them or pass as env vars:
```bash
source .venv/bin/activate
# Use values from .env.local for JWT_SECRET_KEY, ALCHEMY_VAULT_KEY, etc.
ENV=development \
  DATABASE_URL="sqlite+aiosqlite:////absolute/path/to/repo/data/alchemy.db" \
  JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  ALCHEMY_VAULT_KEY="$ALCHEMY_VAULT_KEY" \
  python -m uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000
```

### Important: DATABASE_URL path
- The `database.py` module has a URL slash-counting bug: if the URL has 4+ total slashes, it prepends `/` making the path absolute.
- **Always use an absolute path** with 4 slashes: `sqlite+aiosqlite:////home/ubuntu/repos/alchemy/data/alchemy.db`
- Using relative `./data/alchemy.db` may resolve to `/data/alchemy.db` (permission denied).
- Create the `data/` directory first: `mkdir -p data`

### Verify startup
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.7.0","env":"development"}
```

On first startup, the admin user is auto-created using credentials from `ADMIN_EMAIL` and `ADMIN_PASSWORD` env vars (defaults in `.env.local`).

## Dev Credentials
All dev credentials are stored in `.env.local` at the repo root. Key values:
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — admin login
- `JWT_SECRET_KEY` — JWT signing key
- `ALCHEMY_VAULT_KEY` — vault encryption key

## Devin Secrets Needed
No external secrets required for local dev testing. All credentials are in `.env.local`.

## API Endpoint Patterns

Routes are mounted under both `/api/...` and bare `/...` prefixes.

### Auth endpoints (`/api/auth/...`)
- `POST /api/auth/signup` — `{email, username, full_name, password}`
- `POST /api/auth/login` — `{email, password}` -> returns `{access_token}`
- `POST /api/auth/refresh` — uses `refresh_token` cookie
- `POST /api/auth/logout` — requires Bearer token
- `GET /api/auth/me` — requires Bearer token

### OTP / 2FA endpoints (`/api/auth/otp/...`)
- `POST /api/auth/otp/2fa/setup/init` — requires Bearer token -> returns TOTP `secret` and `qr_code`
- `POST /api/auth/otp/2fa/setup/confirm` — `{totp_code}` + Bearer token
- `POST /api/auth/otp/2fa/disable` — `{totp_code}` + Bearer token
- `GET /api/auth/otp/2fa/status` — requires Bearer token

### Token endpoints (`/api/tokens/...`)
- `POST /api/tokens/register` — requires Bearer token + 2FA
- `POST /api/tokens/{exchange}/validate` — requires Bearer token (no 2FA)
- `GET /api/tokens/status` — requires Bearer token
- `DELETE /api/tokens/{exchange}` — requires Bearer token

## Testing Auth Flows via curl

### Get an auth token
```bash
# Use ADMIN_EMAIL and ADMIN_PASSWORD from .env.local
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"'$ADMIN_EMAIL'","password":"'$ADMIN_PASSWORD'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Use auth token in requests
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me
```

### Generate TOTP codes
```bash
python3 -c "import pyotp; print(pyotp.TOTP('YOUR_SECRET').now())"
```

## Known Pre-existing Issues

1. **Schema mismatch in `otp_routes.py`**: Raw SQL uses column `totp_secret` but the ORM model defines `totp_secret_enc`. This may block the full 2FA setup/disable flow at the DB write step. The `TOTPManager.verify()` call works fine — it's the subsequent `UPDATE users SET totp_secret=...` that might fail.

2. **CI test failures in `test_token_workflow.py`**: 10 tests may fail with `FileNotFoundError: '/home/runner/.alchemy/vault/.salt'`. These are pre-existing on `main` and not marked as required checks.

3. **Token registration requires 2FA**: The `POST /api/tokens/register` endpoint has a `require_2fa` dependency. To test token validate without 2FA, insert tokens directly into the `exchange_tokens` SQLite table.

## Testing Tips

- All testing is shell-only via `curl` — no browser/recording needed for API-only changes.
- The app uses both async SQLAlchemy ORM and raw `sqlite3` connections. Bugs often arise from mismatches between these two layers (column names, table names).
- In dev mode, OTP codes are returned in the API response (no SMTP needed).
- Rate limiting is active even in dev mode. Use `POST /api/auth/rate-limit/reset` to clear.
