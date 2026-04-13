# Alchemy AI Trading Platform — Changelog

**Application:** Alchemy AI Trading Platform  
**Production:** https://akilamirthya.in  
**Repository:** https://github.com/jaikumararjunan/alchemy

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the full versioned architecture, end-to-end flows, and platform roadmap see:
- [`docs/PLATFORM_EVOLUTION.md`](docs/PLATFORM_EVOLUTION.md)
- [`docs/API_GATEWAY_MICROSERVICES.md`](docs/API_GATEWAY_MICROSERVICES.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## [Unreleased] — v1.0.0 — *Horizon* (Planned Q3 2026)

### Added
- **8 independent microservices** — Auth, Trading, Market Data, Intelligence, Risk, Notification, Admin, WebSocket Hub
- **PostgreSQL + TimescaleDB** replacing SQLite in production
- **React Native mobile app v1.0** — iOS (App Store) + Android (Google Play)
  - Full trading, watchlist, alerts, push notifications, biometric auth
  - Offline-first with WatermelonDB sync
- **Celery + Redis task queue** — Background jobs out of web workers
- **GraphQL API** — Strawberry at `/graphql` alongside REST
- **Kubernetes Helm chart** — HPA for Market Data and WebSocket Hub
- **CDN** — Cloudflare for static assets (50ms → 5ms global)
- **mTLS** — Kong mTLS plugin for inter-service security
- **Jaeger distributed tracing** — End-to-end span propagation
- **PgBouncer** — PostgreSQL connection pooling
- **React Native push notifications** — FCM + APNS live delivery

### Changed
- All microservices use RS256 JWT (asymmetric keys, public key distributed)
- Per-service PostgreSQL database schemas
- WebSocket Hub scales to 5 replicas (Redis pub/sub backbone)

---

## [Unreleased] — v0.9.0 — *Nexus* (Planned Q2 2026)

### Added
- **Kong API Gateway** — Single entry point for all clients (web, mobile, bots)
  - JWT verification offloaded from services to gateway
  - `/api/v1/` URL versioning prefix on all routes
  - Response caching for market data (2-second TTL via Kong Proxy Cache plugin)
  - WebSocket passthrough with JWT token verification
  - Canary deployment support (% traffic routing)
  - Per-plan rate limiting (free/pro/team/enterprise) backed by Redis
- **Redis Rate Limiter** (`RedisRateLimiter`) — Replaces `InMemoryRateLimiter`
  - Shared across all workers and containers
  - Survives deploys (no drift on redeploy)
  - Per-user rate limits (not just per-IP) in production mode
- **Redis WebSocket Pub/Sub** — Replaces in-memory `ConnectionManager`
  - Broadcasts work across multiple uvicorn workers and containers
  - Kill-switch propagates via Redis key `alchemy:kill_switch` (no singleton dependency)
  - Supports 5,000+ concurrent WebSocket connections
- **Refresh Token API** — Full dual-token authentication for mobile
  - `POST /api/v1/auth/refresh` — Rotate refresh token (30-day TTL)
  - `POST /api/v1/auth/revoke` — Blacklist token on logout
  - Refresh tokens stored as SHA-256 hashes in `user_sessions` with device fingerprint
  - Web: HttpOnly Secure cookie; Mobile: iOS Keychain / Android Keystore
- **Push Notification Infrastructure**
  - `push_tokens` table — `(user_id, device_token, platform, last_seen_at)`
  - `POST /api/v1/push/register` — Register FCM/APNS device token
  - `POST /api/v1/push/revoke` — Remove token on logout
  - Price alert trigger → FCM (Android) + APNS (iOS) delivery pipeline
  - Firebase Admin SDK + APNs HTTP/2 providers
- **Market Data Redis Cache**
  - Spot prices cached in Redis with 2-second TTL
  - Order book cached at 10-second TTL
  - P95 latency for cached prices: 350ms → 15ms
- **Async Task Queue** (Celery + Redis)
  - Daily analytics, P&L tear-sheet generation moved to background workers
  - Notification dispatch (email, Telegram, WhatsApp, push) fully async
  - Scheduled strategy evaluation out of web worker
- **OpenTelemetry tracing** — `traceparent` header propagated to all services
- **Offline sync** — `?since=<unix_ts>` delta sync on watchlist and alerts endpoints
- **Sparse fieldsets** — `?fields=price,symbol` projection on market data endpoints
- **CDN static assets** — Cloudflare proxy for `/assets/*` (global edge caching)
- **API versioning** — `/api/v1/` prefix on all routes; `Accept-Version` header support
- **Comprehensive documentation**
  - `docs/API_GATEWAY_MICROSERVICES.md` — Full gateway + microservices + end-to-end flows
  - `docs/PLATFORM_EVOLUTION.md` — Versioned roadmap, all recommendations, feature matrix

### Changed
- `docker-compose.prod.yml` — Kong and Redis added as first-class services
- `alchemy/auth/middleware.py` — `InMemoryRateLimiter` replaced by `RedisRateLimiter`
- `alchemy/api/app.py` — `ConnectionManager` replaced by `RedisConnectionManager`
- `alchemy/api/app.py` — `APIRouter(prefix="/api")` → `APIRouter(prefix="/api/v1")`
- `alchemy/api/crypto_routes.py` — Redis cache layer on all price endpoints
- `alchemy/api/auth_routes.py` — New refresh + revoke endpoints
- All Kong-managed security (JWT, rate limiting, CORS) moves from FastAPI middleware to gateway

### Security
- JWT RS256 upgrade (asymmetric keys — private key in Auth Service, public key at gateway)
- Refresh token device fingerprinting prevents token theft from one device used on another
- CSRF protection via SameSite cookie attribute + CSRF token
- Per-user rate limiting (not just per-IP) via Kong consumer groups
- Redis-backed OTP store (replaces in-memory — OTPs survive restarts)

---

## [0.8.0] — 2026-04-13 — *Atlas*

### Added
- **Watchlist** — Per-user symbol watchlist (`/watchlist` page + `/api/watchlist` REST API)
  - Add/remove/edit symbols with optional notes and target prices
  - Upsert semantics: adding a duplicate symbol updates its metadata
  - SQLite table `watchlist_items` created with auto-migration on startup
- **Price Alerts** — Threshold-based price alerts (`/alerts` page + `/api/alerts` REST API)
  - Create `above` / `below` alerts for any symbol on any exchange
  - Alert states: `active → triggered → disabled`
  - `POST /api/alerts/check` evaluates active alerts against supplied prices
  - SQLite table `price_alerts` with indexed `(user_id, status)` for fast lookup
- **CVaR / Expected Shortfall** (`alchemy/risk/cvar.py`)
  - `expected_shortfall(returns, confidence=0.95)` — coherent risk measure per Basel III/IV
  - `kelly_fraction(win_rate, avg_win, avg_loss, fraction=0.25)` — Quarter-Kelly position sizing
  - `portfolio_cvar(position_returns, weights)` — weighted portfolio CVaR
  - `annualise_cvar(daily_cvar)` — √T scaling for annualisation
- **CVaR enrichment on `/api/risk/status`** — Response now includes `cvar_95`, `var_95`,
  `kelly_fraction`, and `worst_loss_pct` computed from user's last 100 trades
- **End-to-end Architecture Documentation** (`docs/ARCHITECTURE.md`)
  - 18-section reference covering system overview, tech stack, data flows, security,
    deployment, observability, API summary, and known constraints
- **18 unit tests** for CVaR module (`tests/unit/test_cvar.py`) — all passing

### Changed
- `alchemy/api/database.py`: added `_get_sqlite_db_path()` public helper for raw sqlite3
  access (used by watchlist and alert routes, consistent with token_routes pattern)
- `frontend/src/components/layout/Layout.jsx`: added **Watchlist** (Markets group) and
  **Price Alerts** (Configuration group) to sidebar navigation
- `frontend/src/App.jsx`: registered `/watchlist` and `/alerts` protected routes

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

MAJOR: Breaking API or DB schema changes requiring migration
MINOR: New features, backward compatible
PATCH: Bug fixes, security patches only
```

## Release Codenames

| Version | Codename | Theme | Status |
|---|---|---|---|
| 0.4.0 | Genesis | Foundation | ✅ Released |
| 0.5.0 | Quantum | Trading engine | ✅ Released |
| 0.6.0 | Stellar | Security + subscriptions | ✅ Released |
| 0.7.0 | Meridian | Admin + stability | ✅ Released |
| 0.8.0 | Atlas | Risk + watchlist | ✅ Released |
| 0.9.0 | Nexus | API Gateway + Redis + Mobile prep | 🔄 In development |
| 1.0.0 | Horizon | Full microservices + mobile app | 📋 Planned Q3 2026 |
| 1.1.0 | Apex | ML predictions + copy trading | 📋 Planned Q4 2026 |
| 2.0.0 | Zenith | White-label + enterprise API | 📋 Planned Q2 2027 |

## Upgrade Notes

### 0.8.x → 0.9.0
- **API URL change:** All routes now under `/api/v1/` (from `/api/`). Update any hardcoded API URLs.
- **Redis required:** Add `REDIS_URL=redis://:password@redis:6379/0` to `.env.production`
- **New Docker service:** Kong gateway added to `docker-compose.prod.yml`
- **No DB migration needed** — new tables (`push_tokens`) are auto-created on startup
- Run `alchemy-update` after updating `.env.production`

### 0.7.x → 0.8.0
- **No manual DB migration needed** — `create_tables()` auto-migrates on startup
- CVaR columns computed dynamically from trade history — no schema change

### 0.6.x → 0.7.0
- **No manual DB migration needed** — `create_tables()` auto-migrates on startup
- If `ADMIN_PASSWORD` in `.env.production` has no special character, update it:
  ```bash
  # .env.production
  ADMIN_PASSWORD=YourNew#Password2024!
  ```
- Run `alchemy-update` after updating `.env.production`

### 0.x → 1.0.0 (SQLite → PostgreSQL)
```bash
# One-time migration — run before upgrading
pip install pgloader
pgloader sqlite:////data/alchemy.db postgresql://alchemy:pass@localhost/alchemy
# Update .env.production:
DATABASE_URL=postgresql+asyncpg://alchemy:pass@postgres:5432/alchemy
```

