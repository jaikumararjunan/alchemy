# Alchemy AI Trading Platform — AI Development Context

> **For Claude / AI assistants:** Read this file FIRST before making any changes.
> Always analyse the repository structure before suggesting solutions.

## Repository
- **GitHub:** https://github.com/jaikumararjunan/alchemy
- **Production:** https://akilamirthya.in
- **Branch:** `main` (protected — CI must pass)

## Quick Start (Local Dev)
```powershell
# Windows
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.local.txt
cd frontend && npm install && npm run build && cd ..
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
# Login: admin@alchemy.in / Alchemy#Admin!2024
```

## Architecture — Read Before Modifying

### Backend Structure
```
alchemy/
├── api/
│   ├── app.py              ← FastAPI app, lifespan, WS routing (WS BEFORE StaticFiles)
│   ├── auth_routes.py      ← Login/signup/refresh — uses RAW sqlite3 (not ORM)
│   ├── admin_routes.py     ← User management, audit logs, stats
│   ├── token_routes.py     ← Exchange credentials (SQLite + AES-256-GCM vault)
│   ├── crypto_routes.py    ← Binance/Delta market data + orders
│   ├── intelligence_routes.py ← AI signals, EI state, strategy generation
│   ├── otp_routes.py       ← Email OTP + TOTP 2FA endpoints
│   ├── metrics.py          ← Prometheus /metrics endpoint
│   └── database.py         ← SQLAlchemy async engine + AUTO-MIGRATIONS
├── auth/
│   ├── middleware.py       ← Rate limiter (localhost bypass in dev), JWT validation
│   ├── security.py         ← bcrypt, JWT, TOTP manager, CSP headers
│   ├── feature_gate.py     ← Subscription-based feature enforcement
│   └── otp_store.py        ← SHA-256 hashed OTP, 10-min TTL
├── core/
│   ├── config.py           ← Pydantic settings (reads .env.local or .env.production)
│   └── messages.py         ← ALL user-facing strings (edit here to change messages)
├── users/models.py         ← SQLAlchemy User, UserSession, AuditLog ORM models
├── notifications/
│   └── email_service.py    ← SMTP email with HTML OTP templates
└── analytics_db/store.py  ← Trade P&L storage
```

### Frontend Structure
```
frontend/src/
├── pages/auth/
│   ├── LoginPage.jsx           ← JWT login, structured error handling
│   ├── SignupPage.jsx           ← Auto-sanitises username, no HTML pattern attr
│   ├── ForgotPasswordPage.jsx  ← Email → reset link
│   ├── ResetPasswordPage.jsx   ← Token from URL → new password
│   └── TwoFASetupPage.jsx      ← 4-step TOTP wizard
├── pages/
│   ├── DashboardPage.jsx
│   ├── CryptoPage.jsx          ← Uses LiveChart component
│   ├── TokenManagerPage.jsx    ← Exchange credentials UI
│   ├── AdminDashboard.jsx      ← User management, delete, subscription
│   └── SubscriptionPage.jsx   ← Plan comparison
├── components/
│   ├── layout/Layout.jsx       ← Desktop sidebar + mobile bottom tab bar
│   └── charts/LiveChart.jsx    ← SVG chart (ChartCanvas OUTSIDE LiveChart = stable)
├── context/AuthContext.jsx     ← tokenRef pattern (no stale closure)
└── store/index.js              ← Zustand store (portfolio NAV, P&L, WS state)
```

## Critical Rules — DO NOT Break These

### Database
- **Production DB path:** `/data/alchemy.db` (Docker volume: `/var/lib/alchemy → /data`)
- **All modules MUST read `DATABASE_URL` env var** — never hardcode `data/alchemy.db`
- `database.py create_tables()` runs auto-migrations on startup (ALTER TABLE ADD COLUMN)
- `auth_routes.py` uses raw `sqlite3` for login (bypasses ORM for performance)
- `token_routes.py` uses raw `sqlite3` for exchange tokens

### Auth Flow
- New users start as `status=pending`; dev mode auto-activates them
- Login checks: pending → auto-activate in dev, error in prod
- JWT secret MUST come from `get_config().jwt_secret_key` — never a default string
- Rate limiter bypasses `127.0.0.1` in dev mode

### React Rules
- `ChartCanvas`, `RSIPanel`, `MACDPanel` MUST be defined OUTSIDE `LiveChart` — they use `React.memo`
- Auth pages use `<PublicRoute>` wrapper; app pages use `<ProtectedRoute>`
- Never use HTML `pattern=` attribute with `-` in character class (Chrome v-flag bug)
- Username field: sanitise in `onChange` with `/^[a-zA-Z0-9_]*/`, no HTML pattern

### WebSocket
- WS routes registered BEFORE `app.mount("/", StaticFiles(...))` — else Starlette asserts
- SPA served via `@app.get("/{full_path:path}")` catch-all, NOT StaticFiles mount

## Known Bug History (Don't Re-Introduce)

| Bug | Root Cause | Fix Applied |
|-----|-----------|-------------|
| Black screen on /crypto | ChartCanvas defined inside LiveChart, remounted on every WS tick | Moved to module level + React.memo |
| Login 500 | `log` not defined in auth_routes.py | `import structlog; log = structlog.get_logger()` |
| Signup 500 | `audit_logs.timestamp` column missing (manual DB had `created_at`) | Auto-migration in create_tables() |
| Login 401 | Admin password auto-generated without special chars, fails PasswordPolicy | Seed ensures password meets policy |
| Token 500 | token_routes used `Path("data/alchemy.db")` not DATABASE_URL | Fixed to read env var |
| WS 500 | StaticFiles caught WS upgrade → `assert scope["type"] == "http"` | WS routes first, no root mount |
| Rate limit lockout | 5 attempts/15min locked out localhost | Dev mode bypasses 127.0.0.1 |
| pip conflict | `langchain-core==0.2.7` + Python 3.12.4 requires `pydantic>=2.7.4` | Removed langchain, pin `pydantic>=2.7.4` |
| Docker readonly DB | Container runs as uid 1000, volume mounted as root | `user: "0:0"` in docker-compose |

## Environment Variables

### Required
```env
JWT_SECRET_KEY=<40+ chars, special chars>
ALCHEMY_VAULT_KEY=<40+ chars, special chars>
DATABASE_URL=sqlite+aiosqlite:////data/alchemy.db
ADMIN_EMAIL=admin@alchemy.in
ADMIN_PASSWORD=<must have upper+lower+digit+special>
ENV=production
```

### Optional (Email OTP)
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=<16-char Gmail App Password>
```

## Subscription Plans
```python
# alchemy/auth/feature_gate.py
PLANS = {"free": 0, "pro": 1, "team": 2, "enterprise": 3}
# check_feature(user.subscription, "trading.live")  → raises 403 if insufficient
# get_limit(user.subscription, "candles")           → -1 = unlimited
```

## Deployment
```bash
# Production (VPS)
cd /opt/alchemy && git pull
docker compose -f docker-compose.production.yml build --no-cache
docker compose -f docker-compose.production.yml up -d

# Update command
alchemy-update   # zero-downtime rolling restart
```

## API Endpoints Summary
- `POST /api/auth/login` — email + password → JWT
- `POST /api/auth/signup` — creates user, auto-activates in dev
- `POST /api/auth/otp/send` — email OTP
- `POST /api/auth/otp/2fa/setup/init` — TOTP QR code
- `DELETE /api/admin/users/{id}` — permanent delete (cascades)
- `PATCH /api/admin/users/{id}/subscription?plan=pro` — change plan
- `GET /metrics` — Prometheus metrics
- `WS /ws` — real-time feed (portfolio, signals, emergency stop)
