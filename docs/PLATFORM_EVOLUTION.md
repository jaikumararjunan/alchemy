# Alchemy AI Trading Platform — Platform Evolution & Complete Recommendations

**Application Name:** Alchemy AI Trading Platform  
**Web Application URL:** https://akilamirthya.in  
**Repository:** https://github.com/jaikumararjunan/alchemy  
**Document Version:** 0.9.0 · April 2026

---

## Table of Contents

1. [Application Identity](#1-application-identity)
2. [Complete Version History](#2-complete-version-history)
3. [All Recommendations — Enhanced & Prioritized](#3-all-recommendations--enhanced--prioritized)
   - 3.1 [Critical — Fix Before Scaling](#31-critical--fix-before-scaling)
   - 3.2 [High Priority — Next Sprint](#32-high-priority--next-sprint)
   - 3.3 [Medium Term — Architecture Evolution](#33-medium-term--architecture-evolution)
   - 3.4 [Long Term — Platform Excellence](#34-long-term--platform-excellence)
4. [End-to-End Architecture Overview](#4-end-to-end-architecture-overview)
5. [Technology Upgrade Path](#5-technology-upgrade-path)
6. [Feature Entitlement Matrix](#6-feature-entitlement-matrix)
7. [Mobile Application Roadmap](#7-mobile-application-roadmap)
8. [Performance Targets](#8-performance-targets)
9. [Security Hardening Checklist](#9-security-hardening-checklist)
10. [Developer Quick Reference](#10-developer-quick-reference)

---

## 1. Application Identity

| Property | Value |
|---|---|
| **Application Name** | Alchemy AI Trading Platform |
| **Short Name** | Alchemy |
| **Production URL** | https://akilamirthya.in |
| **Admin URL** | https://akilamirthya.in/admin |
| **API Docs** | https://akilamirthya.in/docs |
| **Repository** | https://github.com/jaikumararjunan/alchemy |
| **Current Version** | 0.8.0 (Atlas) |
| **Next Release** | 0.9.0 (Nexus) |
| **License** | Proprietary |
| **Stack** | FastAPI · React 18 · PostgreSQL · Redis · Kong |
| **Target Markets** | Indian retail + institutional traders |
| **Supported Exchanges** | Binance, Delta Exchange, Angel Broking, Zerodha Kite |

### Version Codenames

| Version | Codename | Theme |
|---|---|---|
| 0.4.0 | Genesis | Foundation |
| 0.5.0 | Quantum | Trading engine |
| 0.6.0 | Stellar | Security + subscriptions |
| 0.7.0 | Meridian | Admin + stability |
| 0.8.0 | Atlas | Risk + watchlist |
| **0.9.0** | **Nexus** | **API Gateway + Redis + Mobile prep** |
| **1.0.0** | **Horizon** | **Full microservices + mobile app** |
| 1.1.0 | Apex | ML predictions + copy trading |
| 2.0.0 | Zenith | White-label + enterprise API |

---

## 2. Complete Version History

### v0.4.0 — Genesis (2026-04-02)
*Foundation release. First deployable version of Alchemy.*

**Introduced in this version:**
- FastAPI + React 18 application scaffold
- JWT authentication (login / signup / refresh / logout)
- bcrypt password hashing (cost factor 12)
- SQLAlchemy async ORM with SQLite
- User model with roles: `super_admin`, `admin`, `trader`, `analyst`, `viewer`
- Session management with refresh token rotation
- Password strength validation (NIST SP 800-63B)
- Dashboard with live BTC price widget
- Docker multi-stage build (Node frontend + Python backend)
- Initial pytest test suite (134 unit tests)
- GitHub Actions CI/CD pipeline

**Architecture at this version:**
```
Browser → Nginx → FastAPI (single process) → SQLite
```

---

### v0.5.0 — Quantum (2026-04-03)
*Trading engine release. Full exchange connectivity and AI strategies.*

**Introduced in this version:**
- **4 Exchange connections:** Binance, Delta Exchange, Angel Broking, Zerodha Kite
- **Live candlestick chart** (pure SVG): Candle/Line/Area modes
- **Technical indicators:** RSI, MACD, Bollinger Bands, EMA overlay
- **Real-time order book** (@depth10@100ms — 10 bid/ask levels with heat-map bars)
- **Live trade feed** (@trade stream from Binance)
- **Multi-symbol ticker strip** (6 symbols, single WebSocket connection)
- **AI Strategy Engine:** Scalping, Momentum, Breakout, News-Driven strategies
- **Emotional Intelligence (EI) system:** Fear & Greed index, 5 market regime detection
- **News Intelligence Crawlers:** 10 RSS feeds, geo-political event detection
- **Risk Management:** Emergency stop, position limits, blocked ticker list
- **Analytics module:** P&L chart, trade history, strategy performance
- **Token Manager:** AES-256-GCM encrypted exchange credential storage
- **Admin Panel:** User list, ban/unlock, audit logs, platform stats
- **Notification dispatcher:** Telegram, WhatsApp, SMS provider architecture
- **ChromaDB** vector store for semantic market memory (LLM context)

**Bugs fixed:**
- JWT secret mismatch between `auth_routes`, `security.py`, `config.py`
- WebSocket / StaticFiles conflict (WS routes registered before mount)
- Rate limiter blocking localhost in development mode
- SVG path NaN values causing chart render failures on empty data

---

### v0.6.0 — Stellar (2026-04-04)
*Security hardening and subscription monetisation.*

**Introduced in this version:**
- **Email OTP verification:** 6-digit SHA-256 hashed codes, 10-minute TTL
- **TOTP 2FA:** pyotp RFC 6238, Google Authenticator / Authy compatible
- **4-step 2FA Setup Wizard** at `/auth/2fa/setup`
- **Subscription system:** Free / Pro / Team / Enterprise tiers with feature gating
- **SubscriptionPage** at `/subscription` with interactive plan comparison
- **Kubernetes deployment manifests:** namespace, PVC, deployment, service, ingress, HPA
- **Prometheus monitoring:** `/metrics` endpoint, `MetricsMiddleware` per-route counters
- **Grafana dashboards:** Request rate, error rate, latency histograms
- **Alertmanager** with Telegram notifications for production alerts
- **Single-click VPS installer** (`deploy/install.sh`) targeting Hostinger Ubuntu 22.04
- **`alchemy-update`** CLI command for zero-downtime rolling redeploys
- **Mobile-first Layout:** Desktop sidebar + mobile slide-in panel + bottom tab bar
- **`useMobile` React hook** for responsive breakpoint detection
- `alchemy/auth/feature_gate.py` — 30+ feature keys, per-plan numeric limits
- `alchemy/auth/otp_store.py` — In-memory OTP store with TTL enforcement
- `alchemy/notifications/email_service.py` — SMTP HTML email with OTP templates

**Bugs fixed:**
- Black screen on `/crypto`: `ChartCanvas` defined inside `LiveChart` → re-mounted every WS tick
- `MetricsMiddleware` import used before definition (NameError at startup)
- `asyncio.get_event_loop()` deprecated in Python 3.12 → replaced with `get_running_loop()`
- Chrome v-flag regex error on username `pattern=` attribute
- `subscription` column missing from SQLAlchemy ORM model
- WebSocket `AssertionError: scope type must be http` from StaticFiles catching WS upgrades

**Security additions:**
- AES-256-GCM encrypted credential vault for exchange API keys
- CSP headers blocking XSS and external fetch origins
- Rate limiting per endpoint (bypasses localhost in dev mode)
- Fail2ban + UFW firewall rules in production installer

---

### v0.7.0 — Meridian (2026-04-05)
*Admin power tools and developer experience.*

**Introduced in this version:**
- **User deletion** from Admin Panel with full cascade (sessions, audit logs, exchange tokens)
- **Subscription management** from Admin Panel (free/pro/team/enterprise toggle per user)
- **Forgot Password** flow — email → secure reset link → new password page
- **Reset Password** page with live password strength indicator
- **CLAUDE.md** — AI development context file (read-first for all AI coding sessions)
- **RESEARCH.md** — 14-section world-class trading research roadmap
- **SETUP_NOTIFICATIONS.md** — Complete Gmail / Telegram / WhatsApp setup guide
- **CHANGELOG.md** — Version history (this file's predecessor)
- `alchemy/core/version.py` — Single source of truth for application version
- **Auto-migration** in `create_tables()` for missing DB columns (idempotent, safe on redeploy)
- **Centralized messages** in `alchemy/core/messages.py` (all user-facing strings in one place)
- Telegram alert URLs now use `DOMAIN` environment variable instead of localhost
- Admin seed handles duplicate worker `UNIQUE` constraint gracefully on multi-worker startup

**Bugs fixed:**
- 500 on login: `log` variable not defined in `auth_routes.py`
- 500 on signup: `audit_logs.timestamp` column missing in pre-created DB
- 500 on tokens: `token_routes.py` used hardcoded `Path("data/alchemy.db")` not `DATABASE_URL`
- Admin never created: auto-generated `ADMIN_PASSWORD` had no special characters, failed `PasswordPolicy`
- Docker readonly DB: container ran as uid 1000, volume mounted as root
- pip conflict: `langchain-core==0.2.7` + Python 3.12.4 requires `pydantic>=2.7.4`
- Duplicate uvicorn worker admin seeding causing `UNIQUE constraint failed: users.username`
- Analytics DB path using relative `./data/` instead of `DATABASE_URL` environment variable

**Security additions:**
- User deletion blocked for `super_admin` role
- Password reset token expires in 1 hour (cryptographically signed)
- All deletion operations logged to `audit_logs` with actor and target

---

### v0.8.0 — Atlas (2026-04-13)
*Risk intelligence, watchlist, and price alerts.*

**Introduced in this version:**
- **Watchlist** — Per-user symbol watchlist
  - `/watchlist` page with add/remove/edit UI
  - `/api/watchlist` REST API
  - Upsert semantics: duplicate symbol updates metadata
  - SQLite table `watchlist_items` with auto-migration
- **Price Alerts** — Threshold-based price alert system
  - `/alerts` page with alert creation UI
  - `/api/alerts` REST API
  - Alert types: `above` (price crosses up) / `below` (price crosses down)
  - Alert states: `active → triggered → disabled`
  - `POST /api/alerts/check` evaluates active alerts against supplied price map
  - SQLite table `price_alerts` with indexed `(user_id, status)` for fast lookup
- **CVaR / Expected Shortfall** (`alchemy/risk/cvar.py`)
  - `expected_shortfall(returns, confidence=0.95)` — coherent risk measure per Basel III/IV
  - `kelly_fraction(win_rate, avg_win, avg_loss, fraction=0.25)` — Quarter-Kelly position sizing
  - `portfolio_cvar(position_returns, weights)` — weighted portfolio CVaR
  - `annualise_cvar(daily_cvar)` — √T scaling for annualisation
- **CVaR enrichment on `/api/risk/status`** — Response now includes `cvar_95`, `var_95`, `kelly_fraction`, `worst_loss_pct`
- **Trade logic correctness fixes** (v0.9.0 series)
  - `_check_daily_loss` no longer fires on profitable days (was using `abs(pnl)`)
  - `is_kill_switch_active()` now uses `get_risk_manager()` singleton (was creating a new instance)
  - `BreakoutStrategy` SHORT take-profit targets corrected (`support - current` not `resistance - current`)
  - Strategy instances no longer recreated on every scan cycle (moved to `__init__`)
- **End-to-end Architecture Documentation** (`docs/ARCHITECTURE.md`) — 18-section reference
- **268 unit tests** passing (18 new CVaR tests + 56 new trade logic tests)

**Changed:**
- `alchemy/api/database.py`: added `_get_sqlite_db_path()` helper for raw sqlite3 access
- `frontend/src/components/layout/Layout.jsx`: Watchlist + Price Alerts in sidebar navigation
- `frontend/src/App.jsx`: `/watchlist` and `/alerts` registered as protected routes

---

### v0.9.0 — Nexus (Planned — Q2 2026)
*API Gateway, Redis backbone, mobile foundations.*

**Will introduce:**
- **Kong API Gateway** — Single entry point for all clients
  - JWT verification offloaded from services to gateway
  - Per-plan rate limiting (Redis-backed, shared across workers)
  - `/api/v1/` URL versioning prefix
  - Response caching for market data (2-second TTL)
  - WebSocket passthrough with JWT verification
  - Canary deployment support
- **Redis Rate Limiter** — Replace in-memory `InMemoryRateLimiter` with Redis
  - Survives deploys
  - Shared across all workers and containers
  - Per-user (not just per-IP) limits in production
- **Redis WebSocket pub/sub** — Replace in-memory `ConnectionManager`
  - Multiple workers/containers can all broadcast to all connected clients
  - Kill-switch propagates via Redis key (not in-process singleton)
- **Refresh Token API** — Full dual-token auth for mobile
  - `POST /api/v1/auth/refresh` — Rotate refresh token
  - `POST /api/v1/auth/revoke` — Invalidate on logout
  - Refresh tokens stored hashed in `user_sessions` with device fingerprint
- **Push Notification Infrastructure**
  - `push_tokens` table for FCM/APNS device registration
  - `POST /api/v1/push/register` — Register device
  - `POST /api/v1/push/revoke` — Unregister on logout
  - Price alert → FCM/APNS delivery pipeline
- **Market Data Redis Cache**
  - All `GET /api/crypto/prices` responses cached in Redis (2s TTL)
  - Order book cached at 10s TTL
  - Cache miss falls back to exchange REST API
- **API versioning** — `/api/v1/` prefix on all routes
- **Offline-first sync params** — `?since=<unix_ts>` on watchlist and alerts endpoints
- **Sparse fieldsets** — `?fields=price,symbol` projection on market data
- **OpenTelemetry tracing** — `traceparent` header propagated to all services

**Target metrics:**
- P95 API latency: < 200ms (down from current ~350ms)
- WebSocket fan-out: supports 10,000 concurrent connections (up from ~200)
- Rate limiter accuracy: ±0 drift across restarts (was: reset to zero on every deploy)

---

### v1.0.0 — Horizon (Planned — Q3 2026)
*Full microservices decomposition and mobile app launch.*

**Will introduce:**
- **8 independent microservices** (full decomposition — see `docs/API_GATEWAY_MICROSERVICES.md`)
  - Auth Service (8001)
  - Trading Service (8002)
  - Risk Service (8003)
  - Market Data Service (8004) — scales to 10 replicas
  - Intelligence Service (8005)
  - Notification Service (8006)
  - Admin Service (8007)
  - WebSocket Hub (8008) — scales to 5 replicas
- **PostgreSQL + TimescaleDB** — Replace SQLite in production
  - Per-service database schema isolation
  - TimescaleDB extension for time-series (candles, P&L history)
  - Connection pooling via PgBouncer
- **React Native mobile app v1.0**
  - iOS (App Store) + Android (Google Play)
  - Full feature parity with web for trading, watchlist, alerts
  - Push notifications (price alerts, order fills, kill-switch)
  - Biometric authentication (Face ID / fingerprint)
  - Offline-first: cached watchlist, alert history, last signals
  - Dark / light theme auto-switching
- **Celery + Redis task queue** — Move background jobs out of web workers
  - Daily analytics (P&L tear-sheets, CVaR recalculation)
  - Notification dispatch (email, Telegram, WhatsApp)
  - Scheduled strategy evaluation
  - PDF report generation
- **GraphQL API** — Strawberry GraphQL alongside REST at `/graphql`
  - Mobile clients request only needed fields
  - Subscription type for real-time via WebSocket
- **Helm chart** — Kubernetes production deployment
  - HPA on Market Data and WebSocket Hub
  - Pod Disruption Budgets for zero-downtime deploys
  - Secret management via Kubernetes Secrets / HashiCorp Vault
- **CDN** — CloudFront / Cloudflare for static assets and API edge caching
- **Inter-service mTLS** — Kong mTLS plugin for service-to-service security
- **Distributed tracing** — Jaeger with OpenTelemetry spans end-to-end

---

### v1.1.0 — Apex (Planned — Q4 2026)
*ML intelligence, copy trading, TWAP/VWAP execution.*

**Will introduce:**
- **ML Price Prediction** — LightGBM + SHAP feature importance
  - 20-feature engineering pipeline (momentum, volatility, volume, sentiment)
  - 3-regime Hidden Markov Model (bear / consolidation / bull)
  - Temporal Fusion Transformer for multi-horizon forecasting
- **TWAP/VWAP Order Execution** — Large order slicing to minimize market impact
- **Copy Trading** — Follow other traders' signals (Team plan+)
- **VPIN Toxicity Indicator** — Volume-synchronized probability of informed trading
- **Options Analytics** — Greeks (Delta, Gamma, Theta, Vega) display for Kite derivatives
- **Tax Report Generation** — STCG/LTCG report for Indian traders (PDF + CSV)
- **Backtesting Engine v2** — Walk-forward optimization, Monte Carlo simulation
- **LOB Imbalance Indicator** — `(bid_vol - ask_vol) / total_vol` → short-term directional signal

---

### v2.0.0 — Zenith (Planned — Q2 2027)
*White-label, enterprise API, multi-tenancy.*

**Will introduce:**
- **White-label offering** — Custom branding for broker partnerships (Enterprise plan)
- **External API SDK** — Python + JavaScript SDKs for programmatic trading
- **Webhook system** — User-configurable webhooks for order events, signals, alerts
- **Multi-tenancy** — Isolated namespaces for institutional clients
- **FIX protocol adapter** — Connect institutional clients via FIX 4.2/4.4
- **Regulatory reporting** — MIS/CNC position tagging for SEBI compliance
- **Dark pool routing** — For large institutional block orders

---

## 3. All Recommendations — Enhanced & Prioritized

### 3.1 Critical — Fix Before Scaling

These three issues are **blocking** for multi-worker or multi-container deployments:

---

#### REC-001 — Replace In-Memory Rate Limiter with Redis
**Priority:** 🔴 Critical  
**Version Target:** 0.9.0  
**File:** `alchemy/auth/middleware.py`

**Problem:** `InMemoryRateLimiter` stores rate limit buckets in a Python dictionary. It:
1. Resets to zero on every deploy (users get free rate limit refresh on redeploy)
2. Is not shared between uvicorn workers (`--workers 4` means 4 independent limiters)
3. Cannot enforce per-user limits (only per-IP)

**Solution:**
```python
# alchemy/auth/rate_limiter_redis.py
import aioredis
import time

class RedisRateLimiter:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def is_allowed(self, key: str, max_requests: int, window_s: int) -> tuple[bool, int]:
        now = int(time.time())
        window_key = f"ratelimit:{key}:{now // window_s}"
        pipe = self.redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, window_s * 2)
        count, _ = await pipe.execute()
        if count > max_requests:
            retry = window_s - (now % window_s)
            return False, retry
        return True, 0
```

**Impact:** Zero drift rate limiting that works correctly with any number of workers.

---

#### REC-002 — Replace In-Memory WebSocket Manager with Redis Pub/Sub
**Priority:** 🔴 Critical  
**Version Target:** 0.9.0  
**File:** `alchemy/api/app.py` — `ConnectionManager` class

**Problem:** `ConnectionManager.active` is a Python list. If two uvicorn workers run:
- Worker A handles WS connections for user 1, 3, 5
- Worker B handles WS connections for user 2, 4, 6
- A broadcast from Worker B never reaches users on Worker A

**Solution:**
```python
# alchemy/api/ws_manager.py
import aioredis
import asyncio

class RedisConnectionManager:
    CHANNEL = "alchemy:ws:broadcast"

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self.local_connections: list = []

    async def connect(self, ws):
        await ws.accept()
        self.local_connections.append(ws)

    def disconnect(self, ws):
        self.local_connections = [w for w in self.local_connections if w is not ws]

    async def broadcast(self, event: str, data: dict):
        """Publish to Redis — all Hub instances will receive and forward."""
        msg = json.dumps({"event": event, **data})
        await self.redis.publish(self.CHANNEL, msg)

    async def start_listener(self):
        """Listen for broadcasts and forward to local connections."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                dead = []
                for ws in self.local_connections:
                    try:
                        await ws.send_text(message["data"])
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self.disconnect(ws)
```

**Impact:** Horizontal scaling of the WebSocket layer. 10,000+ concurrent connections.

---

#### REC-003 — PostgreSQL Migration
**Priority:** 🔴 Critical  
**Version Target:** 1.0.0 (can be deployed to prod now by changing `DATABASE_URL`)  
**File:** `alchemy/core/config.py`, `docker-compose.prod.yml`

**Problem:** SQLite:
1. Serialises all write operations — one trade at a time
2. Has no connection pool — all SQLAlchemy workers share one file lock
3. Cannot replicate — no read replicas for analytics
4. No TimescaleDB extension for efficient time-series queries

**Solution:** Update `DATABASE_URL` to PostgreSQL. The ORM layer (SQLAlchemy async) requires no changes:
```env
# .env.production
DATABASE_URL=postgresql+asyncpg://alchemy:${DB_PASSWORD}@postgres:5432/alchemy
```

Add `timescale/timescaledb:latest-pg16` container to `docker-compose.prod.yml` (already shown in `docs/API_GATEWAY_MICROSERVICES.md`).

**Migration command:**
```bash
# One-time migration from SQLite to PostgreSQL
pgloader sqlite:////data/alchemy.db postgresql://alchemy:pass@localhost/alchemy
```

**Impact:** Concurrent writes, connection pooling, read replicas, time-series optimization.

---

#### REC-004 — Async Task Queue (Celery + Redis)
**Priority:** 🔴 Critical  
**Version Target:** 0.9.0  
**Files:** `alchemy/scheduler/auto_trader.py`, `alchemy/notifications/dispatcher.py`

**Problem:** Daily analytics, notification dispatch, and scheduled strategy evaluation run inside the web worker. A slow LLM call (2–5 seconds) blocks HTTP responses to other users.

**Solution:** Move to Celery workers with Redis as broker:
```python
# alchemy/tasks/celery_app.py
from celery import Celery

celery = Celery("alchemy", broker="redis://redis:6379/1", backend="redis://redis:6379/2")

@celery.task
def send_notification_task(user_id: str, channel: str, message: str):
    # runs in a separate worker process
    ...

@celery.task
def generate_daily_report_task(user_id: str):
    ...

@celery.task
def evaluate_price_alerts_task(prices: dict):
    ...
```

**Impact:** Web workers respond in <100ms regardless of notification or analytics latency.

---

### 3.2 High Priority — Next Sprint

#### REC-005 — API Versioning (/api/v1/)
**Priority:** 🟡 High  
**Version Target:** 0.9.0  
**File:** `alchemy/api/app.py` line 245

**Current:**
```python
api = APIRouter(prefix="/api")
```

**Target:**
```python
api = APIRouter(prefix="/api/v1")
```

Add `X-API-Version: v1` response header (done at gateway level). Add `Accept-Version` header support for clients that cannot change URLs.

---

#### REC-006 — Refresh Token Rotation (Mobile Auth)
**Priority:** 🟡 High  
**Version Target:** 0.9.0  
**Files:** `alchemy/api/auth_routes.py`, `alchemy/users/models.py`

Implement `POST /api/v1/auth/refresh` and `POST /api/v1/auth/revoke` endpoints. Full specification in `docs/API_GATEWAY_MICROSERVICES.md` §6.4.

---

#### REC-007 — Push Notification Infrastructure
**Priority:** 🟡 High  
**Version Target:** 0.9.0  
**Files:** `alchemy/notifications/providers/`, new `push_tokens` DB table

Add Firebase Admin SDK + APNs HTTP/2 provider. `push_tokens` table schema in `docs/API_GATEWAY_MICROSERVICES.md` §6.2.

---

#### REC-008 — Redis Cache for Market Data
**Priority:** 🟡 High  
**Version Target:** 0.9.0  
**File:** `alchemy/api/crypto_routes.py`

Every `GET /api/crypto/prices` currently hits Binance REST. Add 2-second Redis TTL cache:
```python
async def get_price(symbol: str, redis: Redis):
    cache_key = f"market:price:{symbol}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    price = await binance_client.get_price(symbol)
    await redis.setex(cache_key, 2, json.dumps(price))
    return price
```

**Impact:** P95 latency: 350ms → 15ms for cached symbols.

---

#### REC-009 — Kong API Gateway Deployment
**Priority:** 🟡 High  
**Version Target:** 0.9.5  
**File:** New `deploy/kong.yml`, update `docker-compose.prod.yml`

Full Kong configuration in `docs/API_GATEWAY_MICROSERVICES.md` §3.4 and §13.

---

### 3.3 Medium Term — Architecture Evolution

#### REC-010 — Extract Market Data Service
**Priority:** 🟢 Medium  
**Version Target:** 0.10.0

Market Data is the safest first extraction: stateless (prices are in Redis), no synchronous callers outside trading, and independently scalable. It is the highest-traffic service.

---

#### REC-011 — Extract Notification Service
**Priority:** 🟢 Medium  
**Version Target:** 0.10.0

Fire-and-forget — no synchronous callers. Move to Redis Stream consumer. Trade execution never waits for notification delivery.

---

#### REC-012 — Extract Auth Service
**Priority:** 🟢 Medium  
**Version Target:** 0.11.0

Smallest domain. Once extracted and JWT moves to RS256, other services verify tokens using the public key without calling Auth Service at all.

---

#### REC-013 — GraphQL API
**Priority:** 🟢 Medium  
**Version Target:** 1.0.0

Add Strawberry GraphQL at `/graphql` alongside REST. No rewrite — Strawberry maps directly to existing Pydantic models.

```python
import strawberry
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class Query:
    @strawberry.field
    async def watchlist(self, info) -> list[WatchlistItem]:
        return await get_watchlist(info.context["user_id"])

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def price_tick(self, symbol: str) -> AsyncGenerator[PriceTick, None]:
        async for tick in redis_price_stream(symbol):
            yield tick

schema = strawberry.Schema(query=Query, subscription=Subscription)
app.include_router(GraphQLRouter(schema, prefix="/graphql"))
```

---

#### REC-014 — Kubernetes Helm Chart
**Priority:** 🟢 Medium  
**Version Target:** 1.0.0

Translate existing `docker-compose.prod.yml` to Helm chart. Enable HPA for Market Data (CPU), WebSocket Hub (connection count), and Intelligence Service (CPU). Full structure in `docs/API_GATEWAY_MICROSERVICES.md` §14.

---

#### REC-015 — CDN for Static Assets
**Priority:** 🟢 Medium  
**Version Target:** 0.9.5

React bundle (JS/CSS) served from VPS → high latency for non-Indian users. Move to Cloudflare CDN:
1. Point DNS to Cloudflare (already proxied if using Cloudflare DNS)
2. Enable "Cache Everything" for `/assets/*` paths
3. Keep API (`/api/*`) and WebSocket (`/ws`) bypassing cache

**Impact:** 50ms → 5ms asset load time globally. VPS bandwidth reduced ~60%.

---

### 3.4 Long Term — Platform Excellence

#### REC-016 — ML Price Prediction Pipeline
**Priority:** 🔵 Long term  
**Version Target:** 1.1.0

LightGBM ensemble with 20 engineered features, 3-regime HMM, SHAP interpretability. Full research specification in `RESEARCH.md` §2.

---

#### REC-017 — TWAP/VWAP Order Execution
**Priority:** 🔵 Long term  
**Version Target:** 1.1.0

Almgren-Chriss optimal execution for large orders. Split via `execution/order_pipeline.py`.

---

#### REC-018 — White-Label Enterprise Offering
**Priority:** 🔵 Long term  
**Version Target:** 2.0.0

Multi-tenant architecture, custom branding, FIX protocol adapter, SEBI regulatory reporting.

---

## 4. End-to-End Architecture Overview

See `docs/API_GATEWAY_MICROSERVICES.md` for the full end-to-end flow diagrams. Summary:

```
Mobile App (iOS/Android/React Native)
Web App (React 18 SPA)
3rd-Party Bot (API key)
          │
          ▼  HTTPS/WSS
┌─────────────────────────────────────┐
│         Nginx (TLS + DDoS)          │  ← existing
└──────────────┬──────────────────────┘
               │
               ▼  HTTP (internal)
┌─────────────────────────────────────┐
│       Kong API Gateway              │  ← NEW in v0.9.5
│   JWT verify · Rate limit · Cache   │
│   Route · Version · Canary          │
└──────────────┬──────────────────────┘
               │ routes by /api/v1/{service}/
               ▼
   ┌───────────────────────────────────────────┐
   │           Microservices (v1.0.0)           │
   │  Auth :8001  Trading :8002  Risk :8003     │
   │  Market :8004  AI :8005  Notify :8006      │
   │  Admin :8007  WS-Hub :8008                 │
   └───────────────────────────────────────────┘
               │
   ┌───────────┴─────────────────┐
   │         Shared Data         │
   │  PostgreSQL  Redis  ChromaDB │
   └─────────────────────────────┘
               │
   ┌───────────┴─────────────────┐
   │       Observability         │
   │  Prometheus  Grafana  Loki  │
   │  Jaeger (tracing)           │
   └─────────────────────────────┘
```

---

## 5. Technology Upgrade Path

| Component | v0.8.0 (now) | v0.9.0 | v1.0.0 |
|---|---|---|---|
| **API gateway** | Nginx only | Kong OSS | Kong + K8s Ingress Controller |
| **Rate limiter** | In-memory Python dict | Redis Sorted Set | Kong Rate Limiting plugin |
| **WebSocket** | In-memory list | Redis pub/sub | Redis pub/sub + Hub service |
| **Primary DB** | SQLite | SQLite → PG ready | PostgreSQL + TimescaleDB |
| **Background jobs** | APScheduler (in-process) | Celery + Redis | Celery + Redis (per-service workers) |
| **Push notifications** | None | FCM + APNS infrastructure | Live on iOS + Android |
| **API versioning** | `/api/` | `/api/v1/` | `/api/v1/` + `/api/v2/` canary |
| **Caching** | None | Redis 2s TTL on prices | Multi-layer (Redis + CDN) |
| **Tracing** | structlog only | OpenTelemetry | Jaeger end-to-end |
| **Mobile** | PWA only | PWA + push infra | React Native v1.0 |
| **Auth tokens** | Access only (15min) | Access + Refresh (30d) | Access + Refresh + Device-aware |

---

## 6. Feature Entitlement Matrix

Current feature gate (`alchemy/auth/feature_gate.py`) — complete view:

| Feature | Free | Pro | Team | Enterprise |
|---|---|---|---|---|
| **Trading** | | | | |
| Live trading orders | ✗ | ✅ | ✅ | ✅ |
| All strategy types | ✗ | ✅ | ✅ | ✅ |
| Custom strategy | ✗ | ✗ | ✅ | ✅ |
| TWAP/VWAP execution | ✗ | ✗ | ✅ | ✅ |
| **Exchanges** | | | | |
| 1 exchange | ✅ | ✅ | ✅ | ✅ |
| 2 exchanges | ✗ | ✅ | ✅ | ✅ |
| 4 exchanges | ✗ | ✗ | ✅ | ✅ |
| Unlimited exchanges | ✗ | ✗ | ✗ | ✅ |
| **Charts & Data** | | | | |
| 50 candles | ✅ | ✅ | ✅ | ✅ |
| 500 candles | ✗ | ✅ | ✅ | ✅ |
| 5,000 candles | ✗ | ✗ | ✅ | ✅ |
| Unlimited candles | ✗ | ✗ | ✗ | ✅ |
| Drawing tools | ✗ | ✅ | ✅ | ✅ |
| **AI & Intelligence** | | | | |
| 5 AI ideas/day | ✅ | ✅ | ✅ | ✅ |
| 50 AI ideas/day | ✗ | ✅ | ✅ | ✅ |
| Unlimited AI ideas | ✗ | ✗ | ✅ | ✅ |
| ML prediction | ✗ | ✗ | ✅ | ✅ |
| Custom ML model | ✗ | ✗ | ✗ | ✅ |
| Geo-political signals | ✗ | ✅ | ✅ | ✅ |
| Sentiment NLP | ✗ | ✅ | ✅ | ✅ |
| Premium feeds | ✗ | ✗ | ✅ | ✅ |
| Options analytics | ✗ | ✅ | ✅ | ✅ |
| **Alerts & Notifications** | | | | |
| Email alerts | ✅ | ✅ | ✅ | ✅ |
| Telegram | ✗ | ✅ | ✅ | ✅ |
| Push (mobile) | ✗ | ✅ | ✅ | ✅ |
| WhatsApp | ✗ | ✗ | ✅ | ✅ |
| SMS | ✗ | ✗ | ✅ | ✅ |
| Webhooks | ✗ | ✗ | ✗ | ✅ |
| **Analytics** | | | | |
| CSV export | ✗ | ✅ | ✅ | ✅ |
| JSON export | ✗ | ✗ | ✅ | ✅ |
| Backtesting | ✗ | ✅ | ✅ | ✅ |
| Tax report | ✗ | ✅ | ✅ | ✅ |
| **API & Integrations** | | | | |
| External read API | ✗ | ✗ | ✅ | ✅ |
| External write API | ✗ | ✗ | ✗ | ✅ |
| Webhooks | ✗ | ✗ | ✅ | ✅ |
| SDK | ✗ | ✗ | ✅ | ✅ |
| FIX protocol | ✗ | ✗ | ✗ | ✅ |
| **Team & Admin** | | | | |
| Multi-user | ✗ | ✗ | ✅ | ✅ |
| Audit logs | ✗ | ✗ | ✅ | ✅ |
| Copy trading | ✗ | ✗ | ✅ | ✅ |
| White-label | ✗ | ✗ | ✗ | ✅ |

---

## 7. Mobile Application Roadmap

### v0.9.0 — Infrastructure Ready
- Push token registration API
- Refresh token rotation
- Offline sync params (`?since=`)
- Sparse fieldset params (`?fields=`)

### v1.0.0 — React Native App (iOS + Android)
**Tech stack:**
- React Native 0.73+ with New Architecture (JSI)
- Expo SDK 50 (managed workflow → bare at v1.1)
- React Query (same as web, shared data layer)
- Zustand (same store structure as web)
- React Navigation v6 (stack + tab + modal)
- WatermelonDB (offline SQLite with sync)

**Screens:**
| Screen | Description |
|---|---|
| Login / Signup | Biometric + email auth |
| Dashboard | Portfolio NAV, quick stats |
| Markets | Ticker strip + mini charts |
| Chart | Full candlestick + indicators |
| Order Placement | Market/Limit/Stop-Limit form |
| Portfolio | Positions + P&L |
| Watchlist | Symbol list with alerts |
| Price Alerts | Alert creation + history |
| AI Signals | Latest signals feed |
| Notifications | Alert history + settings |
| Settings | Account, API keys, 2FA |

**Push notification types:**
| Trigger | Notification | Action on tap |
|---|---|---|
| Price alert crossed | "⚡ BTCUSDT crossed $70,000 ↑" | Open alert detail |
| Order filled | "✅ BTC +0.1 @ $68,420 filled" | Open order detail |
| Kill switch activated | "🛑 All trading stopped" | Open risk dashboard |
| New AI signal | "🤖 Strong BUY signal: BTCUSDT" | Open signal detail |
| P&L milestone | "🎯 Daily target reached: +₹5,000" | Open P&L chart |

---

## 8. Performance Targets

| Metric | Current (v0.8.0) | Target (v0.9.0) | Target (v1.0.0) |
|---|---|---|---|
| API P50 latency | 80ms | 40ms | 20ms |
| API P95 latency | 350ms | 100ms | 50ms |
| Market data (cached) | N/A | 15ms | 5ms |
| WebSocket fan-out | ~200 connections | 5,000 | 50,000 |
| Concurrent users | ~100 | 2,000 | 50,000 |
| Order execution | ~800ms | ~400ms | ~200ms |
| Rate limiter accuracy | Resets on deploy | ±0 drift | ±0 drift |
| Uptime SLA | 95% | 99.5% | 99.9% |

---

## 9. Security Hardening Checklist

### Done ✅
- [x] bcrypt cost factor 12 for password hashing
- [x] JWT HS256 with minimum 40-character secret
- [x] AES-256-GCM encrypted exchange credential vault
- [x] CSP headers (via `SecurityHeadersMiddleware`)
- [x] HSTS preload (via Nginx)
- [x] Rate limiting per endpoint (in-memory, to be replaced)
- [x] OTP codes hashed before storage (SHA-256)
- [x] Admin routes not exposed on default Nginx config
- [x] Fail2ban + UFW firewall in production installer
- [x] Password policy (NIST SP 800-63B)
- [x] Super-admin deletion protection
- [x] Audit log for all sensitive operations

### Planned for v0.9.0 🔄
- [ ] Upgrade JWT to RS256 (asymmetric — public key distributable to services)
- [ ] Redis-backed OTP store (replace in-memory, survives restarts)
- [ ] Refresh token device fingerprinting
- [ ] CSRF protection for web forms (SameSite cookie + CSRF token)
- [ ] Rate limiting per user-ID (not just per-IP) via Kong

### Planned for v1.0.0 🔄
- [ ] mTLS for inter-service communication
- [ ] Secrets via Kubernetes Secrets + HashiCorp Vault
- [ ] GitHub Actions secret scanning (Gitleaks)
- [ ] SAST in CI (Bandit for Python, ESLint security plugin for React)
- [ ] Dependency vulnerability scanning (Dependabot)
- [ ] Annual penetration test

---

## 10. Developer Quick Reference

### Running the Platform

```bash
# Local development
py -3.12 -m venv .venv && .venv\Scripts\activate  # Windows
python3.12 -m venv .venv && source .venv/bin/activate  # Linux/Mac
pip install -r requirements.local.txt
cd frontend && npm install && npm run build && cd ..
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload

# Default login: admin@alchemy.in / Alchemy#Admin!2024
```

### Running Tests

```bash
python -m pytest tests/unit/ -v
# Expected: 268 tests, all passing (as of v0.8.0)
```

### Key Environment Variables

```env
# Required
JWT_SECRET_KEY=<40+ chars with special chars>
ALCHEMY_VAULT_KEY=<40+ chars with special chars>
DATABASE_URL=sqlite+aiosqlite:////data/alchemy.db    # dev
DATABASE_URL=postgresql+asyncpg://...                # prod
ADMIN_EMAIL=admin@alchemy.in
ADMIN_PASSWORD=<upper+lower+digit+special>
ENV=production

# Optional (notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=<16-char Gmail App Password>
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<your chat ID>

# New in v0.9.0
REDIS_URL=redis://:password@redis:6379/0
FCM_SERVER_KEY=<Firebase Admin SDK key>
APNS_KEY=<Apple push key>
```

### Production Deploy

```bash
cd /opt/alchemy && git pull
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
# Or: alchemy-update   (zero-downtime rolling restart)
```

### API Base URL

```
https://akilamirthya.in/api/v1/    (v0.9.0+)
https://akilamirthya.in/api/       (v0.8.0 and earlier)
https://akilamirthya.in/docs       (OpenAPI documentation)
https://akilamirthya.in/metrics    (Prometheus metrics)
```

### Documentation Index

| Document | Contents |
|---|---|
| `README.md` | Quick start, setup |
| `CHANGELOG.md` | Full version history |
| `docs/ARCHITECTURE.md` | 18-section architecture reference |
| `docs/API_GATEWAY_MICROSERVICES.md` | API Gateway + microservices + end-to-end flows |
| `docs/PLATFORM_EVOLUTION.md` | This document — recommendations + roadmap |
| `RESEARCH.md` | Trading research roadmap (ML, risk, microstructure) |
| `DEPLOYMENT.md` | VPS deployment guide |
| `SETUP_NOTIFICATIONS.md` | Gmail / Telegram / WhatsApp setup |
| `CLAUDE.md` | AI coding assistant context |
