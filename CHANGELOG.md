# Alchemy Trading Platform — Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.7.0] — 2026-04-05 — *Meridian*

### Added
- **User deletion** from Admin Panel with cascade (sessions, audit logs, exchange tokens)
- **Subscription management** from Admin Panel (free/pro/team/enterprise toggle)
- **Forgot Password** flow — email → reset link → new password page
- **Reset Password** page with live password strength validation
- **CLAUDE.md** — AI development context file (read-first for all AI sessions)
- **RESEARCH.md** — 14-section world-class research roadmap
- **SETUP_NOTIFICATIONS.md** — Complete Gmail/Telegram/WhatsApp setup guide
- **CHANGELOG.md** — This file (version history)
- **alchemy/core/version.py** — Single source of truth for version number
- **Auto-migration** in `create_tables()` for missing DB columns (idempotent)
- **Centralized messages** in `alchemy/core/messages.py` (edit to customize)
- Telegram alert URLs now use `DOMAIN` env var instead of localhost
- Admin seed handles duplicate worker UNIQUE constraint gracefully

### Fixed
- **500 on login**: `log` variable not defined in `auth_routes.py`
- **500 on signup**: `audit_logs.timestamp` column missing in pre-created DB
- **500 on tokens**: `token_routes.py` used hardcoded `Path("data/alchemy.db")` not `DATABASE_URL`
- **Admin never created**: auto-generated `ADMIN_PASSWORD` had no special chars, failed `PasswordPolicy`
- **Docker readonly DB**: container ran as uid 1000, volume mounted as root → `chmod 777 /data`
- **pip conflict**: `langchain-core==0.2.7` + Python 3.12.4 requires `pydantic>=2.7.4`
- Duplicate uvicorn worker admin seeding causing `UNIQUE constraint failed: users.username`
- Analytics DB path using relative `./data/` instead of `DATABASE_URL`

### Security
- User deletion blocked for `super_admin` role
- Password reset token expires in 1 hour
- All deletion operations logged to audit_logs

---

## [0.6.0] — 2026-04-04 — *Stellar*

### Added
- **Email OTP verification**: 6-digit SHA-256 hashed, 10-min TTL
- **TOTP 2FA**: pyotp RFC 6238, Google Authenticator/Authy compatible
- **4-step 2FA Setup Wizard** (`/auth/2fa/setup`)
- **Subscription system**: Free/Pro/Team/Enterprise with feature gating
- **SubscriptionPage** (`/subscription`) with plan comparison
- **Kubernetes deployment** manifests (namespace, PVC, deployment, service, ingress, HPA)
- **Prometheus monitoring**: `/metrics` endpoint, MetricsMiddleware
- **Grafana dashboards** + Alertmanager with Telegram notifications
- **Single-click VPS installer** (`deploy/install.sh`) for Hostinger Ubuntu 22.04
- **`alchemy-update`** command for zero-downtime rolling redeploy
- **Mobile-first Layout**: desktop sidebar + mobile slide-in + bottom tab bar
- **`useMobile` hook** for responsive breakpoint detection
- `alchemy/auth/feature_gate.py` — 30+ feature keys, per-plan limits
- `alchemy/auth/otp_store.py` — in-memory OTP store with TTL
- `alchemy/notifications/email_service.py` — SMTP HTML email with OTP templates

### Fixed
- Black screen on `/crypto`: `ChartCanvas` defined inside `LiveChart` → remounted every WS tick
- `MetricsMiddleware` import used before definition (NameError at startup)
- `asyncio.get_event_loop()` deprecated in Python 3.12 → replaced with `get_running_loop()`
- Chrome v-flag regex error on username `pattern=` attribute
- `subscription` column missing from SQLAlchemy ORM model
- WebSocket `AssertionError: scope type must be http` from StaticFiles catching WS

### Security
- AES-256-GCM encrypted credential vault for exchange API keys
- CSP headers blocking XSS and external fetch
- Rate limiting per endpoint (bypasses localhost in dev)
- Fail2ban + UFW firewall in production installer

---

## [0.5.0] — 2026-04-03 — *Quantum*

### Added
- **4 Exchange connections**: Binance, Delta Exchange, Angel Broking, Zerodha Kite
- **Live candlestick chart** (pure SVG): Candle/Line/Area, RSI, MACD, BB, EMA
- **Real-time order book** (@depth10@100ms, 10 bid/ask levels with heat-map bars)
- **Live trade feed** (@trade stream)
- **Multi-symbol ticker** strip (6 symbols, single WS connection)
- **AI Strategy Engine**: Scalping, Momentum, Breakout, News-Driven
- **Emotional Intelligence (EI)** system: Fear & Greed index, 5 market regimes
- **News Intelligence Crawlers**: 10 RSS feeds, geo-political detection
- **Risk Management**: emergency stop, position limits, blocked tickers
- **Analytics**: P&L chart, trade history, strategy performance
- **Token Manager**: AES-256-GCM encrypted credential storage
- **Admin Panel**: user list, ban/unlock, audit logs, stats
- **Notification dispatcher**: Telegram, WhatsApp, SMS providers
- **ChromaDB** vector store for semantic market memory

### Fixed
- JWT secret mismatch between auth_routes, security.py, config.py
- WebSocket StaticFiles conflict (WS routes registered before mount)
- Rate limiter blocking localhost in development
- SVG path NaN values causing chart render failures

---

## [0.4.0] — 2026-04-02 — *Genesis*

### Added
- Initial FastAPI + React application scaffold
- JWT authentication (login/signup/refresh/logout)
- bcrypt password hashing (cost factor 12)
- SQLAlchemy async ORM with SQLite
- User model with roles (super_admin, admin, trader, analyst, viewer)
- Session management with refresh token rotation
- Password strength validation (NIST SP 800-63B)
- Dashboard with live BTC price
- Docker multi-stage build (Node frontend + Python backend)
- pytest test suite (134 unit tests)

---

## Version Scheme

```
MAJOR.MINOR.PATCH — Codename

MAJOR: Breaking API or DB schema changes
MINOR: New features, backward compatible
PATCH: Bug fixes, security patches
```

## Upgrade Notes

### 0.6.x → 0.7.0
- **No manual DB migration needed** — `create_tables()` auto-migrates on startup
- If `ADMIN_PASSWORD` in `.env.production` has no special character, update it:
  ```bash
  # .env.production
  ADMIN_PASSWORD=YourNew#Password2024!
  ```
- Run `alchemy-update` after updating `.env.production`
# CI trigger 2026-04-05
