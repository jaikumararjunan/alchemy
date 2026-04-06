# Testing Alchemy Auth Flows

## Local Dev Setup

```bash
# Activate venv and install deps
source .venv/bin/activate
pip install -r requirements.local.txt

# Build frontend (served as SPA by backend)
cd frontend && npm install && npm run build && cd ..

# Start server with fresh DB
mkdir -p data
export DATABASE_URL="sqlite+aiosqlite:////home/ubuntu/repos/alchemy/data/alchemy.db"
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
```

## Important: DATABASE_URL

- `.env.local` has `DATABASE_URL=sqlite+aiosqlite:///./data/alchemy.db` (relative path)
- This can cause issues — the path parser in `database.py` may misinterpret it as `/data` (absolute Docker path)
- Always use an absolute path when running locally: `sqlite+aiosqlite:////home/ubuntu/repos/alchemy/data/alchemy.db`

## Admin Credentials

- Email: Value from `ADMIN_EMAIL` in `.env.local` (default: `admin@alchemy.in`)
- Password: Value from `ADMIN_PASSWORD` in `.env.local`
- Admin is auto-seeded on startup via `seed_admin_user()` in app lifespan

## Auth Architecture

- All auth endpoints in `alchemy/api/auth_routes.py` delegate to `AuthService` in `alchemy/auth/service.py`
- Uses SQLAlchemy async sessions (not raw sqlite3)
- New users start as `status=pending`
- In dev mode (`ENV=development/dev/local/test`): pending users are auto-activated on login
- In production/paper mode: pending users are rejected with `account_pending_verification`

## Frontend Routes

- Login: `/auth/login`
- Signup: `/auth/signup`
- Forgot Password: `/auth/forgot-password`
- Reset Password: `/auth/reset-password`
- 2FA Setup: `/auth/2fa/setup`
- Dashboard: `/dashboard`

## Key Test Scenarios

1. **Login** — `POST /api/auth/login` with `{email, password}` returns `{access_token, user}`
2. **Bad password** — Returns 401 with `{code: "invalid_credentials"}`
3. **Signup** — `POST /api/auth/signup` with `{email, username, full_name, password}`. In dev mode, auto-logs in. In production, returns "please verify email".
4. **Logout** — `POST /api/auth/logout` clears refresh_token cookie
5. **Refresh** — `POST /api/auth/refresh` uses refresh_token cookie

## CI Notes

- `Backend Tests` CI job fails on pre-existing `TestTokenVault` / `TestTokenManager` issues (`FileNotFoundError: '/home/runner/.alchemy/vault/.salt'`) — not related to auth
- `Frontend Build` CI job is the reliable check for this repo
- Ruff lint warnings are mostly pre-existing (missing return type annotations, FastAPI `Depends()` patterns)

## Known Gotchas

- Signup `db.commit()` must happen BEFORE auto-login attempt — otherwise pending users in production never get persisted
- Password must meet policy: 12+ chars, uppercase, lowercase, digit, special character
- Rate limiter bypasses `127.0.0.1` in dev mode but can block in other envs
- Chrome password manager popup may cover UI during testing — dismiss with "OK" button
