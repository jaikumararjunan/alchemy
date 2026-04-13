# Alchemy AI Trading Platform — End-to-End Architecture Documentation

**Application:** Alchemy AI Trading Platform  
**Version:** 0.9.0 · **Updated:** April 2026  
**Production:** https://akilamirthya.in  
**Repository:** https://github.com/jaikumararjunan/alchemy

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Backend Architecture](#4-backend-architecture)
   - 4.1 [FastAPI Application Structure](#41-fastapi-application-structure)
   - 4.2 [API Layer (Routes)](#42-api-layer-routes)
   - 4.3 [Authentication & Security](#43-authentication--security)
   - 4.4 [Database Layer](#44-database-layer)
   - 4.5 [Risk Management Engine](#45-risk-management-engine)
   - 4.6 [Intelligence & AI Subsystem](#46-intelligence--ai-subsystem)
   - 4.7 [Notification System](#47-notification-system)
5. [Frontend Architecture](#5-frontend-architecture)
   - 5.1 [React Application Structure](#51-react-application-structure)
   - 5.2 [State Management](#52-state-management)
   - 5.3 [Page & Component Catalogue](#53-page--component-catalogue)
6. [Real-Time Communication](#6-real-time-communication)
7. [Exchange Integrations](#7-exchange-integrations)
8. [Risk & Analytics Pipeline](#8-risk--analytics-pipeline)
   - 8.1 [Pre-Trade Risk Checks](#81-pre-trade-risk-checks)
   - 8.2 [CVaR / Expected Shortfall](#82-cvar--expected-shortfall)
   - 8.3 [Kelly Criterion Position Sizing](#83-kelly-criterion-position-sizing)
9. [Watchlist & Alerts System](#9-watchlist--alerts-system)
10. [Paper Trading](#10-paper-trading)
11. [Deployment Architecture](#11-deployment-architecture)
    - 11.1 [Docker Compose Stack](#111-docker-compose-stack)
    - 11.2 [Kubernetes (Production)](#112-kubernetes-production)
    - 11.3 [CI/CD Pipeline](#113-cicd-pipeline)
12. [Observability & Monitoring](#12-observability--monitoring)
13. [Security Architecture](#13-security-architecture)
14. [Data Flow Diagrams](#14-data-flow-diagrams)
    - 14.1 [Login Flow](#141-login-flow)
    - 14.2 [Order Execution Flow](#142-order-execution-flow)
    - 14.3 [WebSocket Data Flow](#143-websocket-data-flow)
15. [Module Dependency Map](#15-module-dependency-map)
16. [Configuration Reference](#16-configuration-reference)
17. [API Reference Summary](#17-api-reference-summary)
18. [Known Constraints & Decisions](#18-known-constraints--decisions)
19. [API Gateway Architecture (v0.9.0+)](#19-api-gateway-architecture-v090)
20. [Microservices Architecture (v1.0.0)](#20-microservices-architecture-v100)
21. [Mobile Communication Architecture (v0.9.0+)](#21-mobile-communication-architecture-v090)

---

## 1. System Overview

Alchemy is a **multi-exchange AI-powered algorithmic trading platform** designed for Indian retail and institutional traders. It connects to Binance (crypto spot/futures), Delta Exchange (crypto derivatives), Angel Broking, and Zerodha Kite (Indian equities/F&O) through a single unified interface.

### Core Capabilities

| Capability | Description |
|---|---|
| **Multi-exchange connectivity** | Binance, Delta, Angel Broking, Zerodha Kite |
| **Real-time charts** | SVG candlesticks with RSI, MACD, Bollinger Bands, EMA |
| **AI Signals** | LLM-powered trade idea generation with market context |
| **Emotional Intelligence (EI)** | Fear & Greed index with 5 market regime detection |
| **Autonomous trading** | Strategy runner with full risk pipeline |
| **Paper trading** | Simulated trading engine with realistic fills |
| **Risk management** | CVaR, Kelly Criterion, position limits, emergency stop |
| **Watchlist** | Personal symbol tracking with target prices |
| **Price Alerts** | Threshold-based alerts (above/below) for any symbol |
| **Notifications** | Telegram, Gmail, WhatsApp multi-channel alerts |
| **Admin panel** | User management, audit logs, subscription control |

---

## 2. Technology Stack

### Backend

| Component | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.115.x |
| ASGI server | Uvicorn + Gunicorn | — |
| Python | CPython | 3.12 |
| ORM | SQLAlchemy Async | 2.x |
| Database (dev) | SQLite + aiosqlite | — |
| Database (prod) | PostgreSQL / TimescaleDB | 16.x |
| Auth | JWT (python-jose) + bcrypt-12 | — |
| 2FA | pyotp (RFC 6238 TOTP) | — |
| Crypto vault | AES-256-GCM (cryptography) | — |
| Task scheduling | APScheduler | — |
| Logging | structlog (JSON) | — |
| Config | pydantic-settings | 2.x |
| HTTP client | httpx (async) | — |
| WebSocket | FastAPI native (starlette) | — |

### Frontend

| Component | Technology | Version |
|---|---|---|
| Framework | React | 18.x |
| Build tool | Vite | 5.x |
| Styling | TailwindCSS | 3.x |
| Routing | React Router DOM | 6.x |
| Data fetching | TanStack React Query | 5.x |
| State management | Zustand | 4.x |
| Charts | Recharts + custom SVG | — |
| Icons | Lucide React | — |
| HTTP | Axios | — |

### Infrastructure

| Component | Technology |
|---|---|
| Container | Docker + Docker Compose |
| Reverse proxy | Nginx + Let's Encrypt (Certbot) |
| Orchestration (prod) | Kubernetes (k8s manifests provided) |
| Metrics | Prometheus + Grafana |
| Alerting | Alertmanager + Telegram |
| CI/CD | GitHub Actions |
| VPS | Hostinger Ubuntu 22.04 |

---

## 3. High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                          CLIENT TIER                               │
│  Browser / Mobile (PWA)                                            │
│  React 18 + Vite · TailwindCSS · Zustand · React Query            │
│  WebSocket client (real-time: portfolio, signals, alerts)          │
└────────────────────────────┬──────────────────────────────────────┘
                             │  HTTPS / WSS
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│                         EDGE / PROXY TIER                          │
│  Nginx 1.24 (TLS termination, static file serving, rate limit)     │
└────────────────────────────┬──────────────────────────────────────┘
                             │  HTTP (internal)
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│                      APPLICATION TIER                              │
│  FastAPI (ASGI) · Uvicorn workers                                  │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Auth / OTP  │  │  REST APIs   │  │  WebSocket (/ws)          │ │
│  │  JWT + TOTP │  │  20+ routers │  │  ConnectionManager        │ │
│  └─────────────┘  └──────────────┘  └──────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────┐  ┌─────────────────────────────────┐   │
│  │  Intelligence Engine │  │  Risk Management Engine          │   │
│  │  EI · Signals · LLM  │  │  CVaR · Kelly · Kill-switch      │   │
│  └──────────────────────┘  └─────────────────────────────────┘   │
│                                                                    │
│  ┌──────────────────────┐  ┌─────────────────────────────────┐   │
│  │  Exchange Gateways   │  │  Notification Dispatcher         │   │
│  │  Binance · Delta     │  │  Telegram · Email · WhatsApp     │   │
│  │  Angel · Kite        │  └─────────────────────────────────┘   │
│  └──────────────────────┘                                         │
└────────────────────────────┬──────────────────────────────────────┘
                             │
          ┌──────────────────┼─────────────────────┐
          ▼                  ▼                      ▼
┌─────────────────┐ ┌───────────────┐   ┌──────────────────────┐
│   PRIMARY DB    │ │  ANALYTICS DB │   │  EXCHANGE APIS        │
│ SQLite (dev)    │ │  SQLite       │   │  Binance REST/WS      │
│ PostgreSQL (prod│ │  Trades, EI,  │   │  Delta REST           │
│ Users, sessions │ │  P&L, signals │   │  Angel Broking        │
│ Audit logs      │ │               │   │  Zerodha Kite         │
└─────────────────┘ └───────────────┘   └──────────────────────┘
```

---

## 4. Backend Architecture

### 4.1 FastAPI Application Structure

**Entry point:** `alchemy/api/app.py`

The application uses a critical architectural constraint: **WebSocket routes must be registered BEFORE any StaticFiles mount**. Starlette's routing engine routes requests in registration order, so if `StaticFiles` were mounted at `/` first, it would intercept WebSocket upgrade requests causing `AssertionError: scope type must be http`.

```
app (FastAPI)
├── Middleware stack (innermost → outermost)
│   ├── SecurityHeadersMiddleware (CSP, HSTS, X-Frame)
│   ├── CORSMiddleware
│   └── MetricsMiddleware (Prometheus counters)
│
├── /ws  (WebSocket — registered FIRST)
│
├── /api/...  (APIRouter — all REST endpoints)
│   ├── /auth/...
│   ├── /crypto/...
│   ├── /intelligence/...
│   ├── /risk/...
│   ├── /watchlist/...  ← new
│   ├── /alerts/...     ← new
│   └── ...
│
├── /assets  (StaticFiles — CSS/JS/fonts)
│
└── /{full_path:path}  (SPA catch-all → index.html)
```

### 4.2 API Layer (Routes)

Each router is a separate module under `alchemy/api/`:

| Router file | Prefix | Responsibility |
|---|---|---|
| `auth_routes.py` | `/auth` | Login, signup, refresh, password reset |
| `admin_routes.py` | `/admin` | User management, audit logs, stats |
| `token_routes.py` | `/tokens` | Exchange API key vault (AES-256-GCM) |
| `crypto_routes.py` | `/crypto` | Market data proxy, order execution |
| `intelligence_routes.py` | `/intelligence` | AI signals, EI, strategy generation |
| `notification_routes.py` | `/notifications` | Channel CRUD, rules, delivery log |
| `otp_routes.py` | `/auth/otp` | Email OTP + TOTP 2FA endpoints |
| `autonomous_routes.py` | `/autonomous` | Autonomous trading session control |
| `paper_trading_routes.py` | `/paper` | Paper trading engine |
| `investment_routes.py` | `/investments` | Portfolio positions, P&L |
| `capital_routes.py` | `/capital` | Capital allocation management |
| `features_routes.py` | `/features` | Feature gate checks (subscription) |
| `audit_routes.py` | `/audit` | User audit log access |
| `watchlist_routes.py` | `/watchlist` | Symbol watchlist CRUD ← **new** |
| `alert_routes.py` | `/alerts` | Price alert CRUD + evaluation ← **new** |
| `metrics.py` | `/metrics` | Prometheus metrics endpoint |

### 4.3 Authentication & Security

**Auth flow:**

```
POST /api/auth/login
  → AuthService.authenticate(email, password)
  → bcrypt.checkpw (cost=12)
  → check user status (pending/active/locked/banned)
  → issue access_token (JWT, 15min) + refresh_token (JWT, 7d)
  → store refresh_token_hash in user_sessions table
  → return {access_token, refresh_token, user}
```

**JWT structure:**
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "trader",
  "jti": "unique-token-id",
  "exp": 1714000000
}
```

**Security layers:**

| Layer | Implementation |
|---|---|
| Password hashing | bcrypt (cost=12) |
| JWT signing | HS256 with 40+ char secret |
| TOTP 2FA | RFC 6238 via pyotp, time window ±1 |
| Exchange vault | AES-256-GCM with PBKDF2-HMAC-SHA256 |
| Rate limiting | 5 req/15min per IP (dev bypass for 127.0.0.1) |
| CSP | `default-src 'self'` blocking XSS + external fetch |
| HSTS | `max-age=31536000; includeSubDomains` |
| Credential stuffing | >20 failed logins = permanent IP block |

### 4.4 Database Layer

**Primary DB** (`alchemy/api/database.py`):

- Dev: SQLite via `aiosqlite` at `./data/alchemy.db`
- Prod: PostgreSQL (asyncpg driver) via `DATABASE_URL` env var
- Schema managed by SQLAlchemy ORM + auto-migration in `create_tables()`

**Tables (SQLAlchemy ORM):**

| Table | Purpose |
|---|---|
| `users` | User accounts, roles, status, 2FA, subscriptions |
| `user_sessions` | Active JWT sessions (refresh token tracking) |
| `audit_logs` | Immutable audit trail of all sensitive actions |

**Raw SQLite tables** (non-ORM, created by respective modules):

| Table | Module | Purpose |
|---|---|---|
| `exchange_tokens` | `token_routes.py` | AES-encrypted API keys |
| `watchlist_items` | `watchlist_routes.py` | User symbol watchlists |
| `price_alerts` | `alert_routes.py` | Price threshold alerts |

**Analytics DB** (`alchemy/analytics_db/store.py`):

Separate SQLite file (`analytics.db`) with its own schema:

| Table | Purpose |
|---|---|
| `trades` | Trade records with P&L, strategy, EI state at time of trade |
| `ei_states` | Historical Emotional Intelligence readings |
| `video_summaries` | YouTube market analysis summaries |
| `signals` | Market intelligence signals from crawlers |

### 4.5 Risk Management Engine

**`alchemy/risk/`** — comprehensive pre-trade and real-time risk controls:

```
alchemy/risk/
├── manager.py       — Core RiskManager (position limits, daily loss, drawdown)
├── cvar.py          — CVaR / Expected Shortfall + Kelly Criterion  ← new
├── kill_switch.py   — Emergency stop (closes all positions)
├── dedup.py         — Order deduplication (cooldown per symbol/strategy)
├── price_guard.py   — Sanity check on order price vs market price
├── position_sizing.py — Volatility-scaled position sizing
├── reconciler.py    — Exchange position reconciliation
└── audit_log.py     — Risk decision audit trail
```

**Pre-trade checks (in order):**
1. Signal is actionable (not HOLD)
2. Daily loss limit not breached
3. Max open positions not exceeded
4. Max drawdown circuit breaker not triggered
5. Volatility regime override (block new longs in extreme vol)
6. Position size adjusted for volatility scaling
7. Stop loss / take profit validation

**CVaR enrichment on `/risk/status`:**

The risk status endpoint now enriches its response with CVaR metrics computed from the user's last 100 trades:
- `cvar_95` — 95th percentile CVaR (% of capital)
- `var_95` — 95th percentile VaR
- `kelly_fraction` — Quarter-Kelly recommended position size
- `worst_loss_pct` — Single worst historical trade

### 4.6 Intelligence & AI Subsystem

```
alchemy/intelligence/
├── crawlers/
│   ├── market_crawler.py  — News crawler orchestrator (NewsAPI, RSS)
│   └── video_crawler.py   — YouTube transcript + LLM summariser
└── emotion/
    └── ei_engine.py       — Emotional Intelligence (Fear & Greed, regime detection)

alchemy/trading/strategies/
└── engine.py              — Strategy orchestrator (Scalping, Momentum, Breakout, News)

alchemy/llm/               — LLM gateway (LiteLLM proxy, Claude/GPT/Gemini)
alchemy/signals/engine.py  — Signal aggregation + scoring
```

**EI (Emotional Intelligence) state:**

```
EI Score = f(
  RSI(14),
  Bollinger Band width,
  Volume z-score,
  News sentiment score,
  Social sentiment score
)
→ Fear & Greed Index (0-100)
→ Regime: {extreme_fear, fear, neutral, greed, extreme_greed}
→ Position size multiplier (0.25x in extreme fear, 1.5x in greed)
```

### 4.7 Notification System

```
alchemy/notifications/
├── dispatcher.py    — Fan-out to all active channels for a user
├── email_service.py — SMTP/Gmail with HTML templates
├── models.py        — Channel, Rule, Event schemas
└── providers/
    ├── telegram.py
    ├── whatsapp.py
    └── registry.py  — Provider auto-discovery
```

Notification rules can be triggered by events: `TRADE_EXECUTED`, `STOP_LOSS_HIT`, `AI_SIGNAL`, `DAILY_SUMMARY`, `EMERGENCY_STOP`, etc.

---

## 5. Frontend Architecture

### 5.1 React Application Structure

```
frontend/src/
├── main.jsx              — ReactDOM.createRoot, QueryClientProvider, BrowserRouter
├── App.jsx               — Route definitions (public + protected)
├── index.css             — Tailwind base + custom utilities
│
├── api/                  — API client factory
├── components/
│   ├── auth/
│   │   └── ProtectedRoute.jsx   — Route guard (JWT check + admin role check)
│   ├── charts/
│   │   └── LiveChart.jsx        — SVG candlestick chart (defined OUTSIDE component)
│   └── layout/
│       └── Layout.jsx           — Sidebar (desktop) + bottom tab bar (mobile)
│
├── context/
│   └── AuthContext.jsx          — tokenRef pattern (avoids stale closures)
│
├── hooks/
│   ├── useAlchemySocket.jsx     — WebSocket connection + message dispatch
│   └── useMobile.js             — Responsive breakpoint detection
│
├── pages/
│   ├── auth/               — LoginPage, SignupPage, ForgotPassword, ResetPassword, TwoFASetup
│   ├── admin/              — AdminDashboard
│   ├── DashboardPage.jsx
│   ├── PortfolioPage.jsx
│   ├── CryptoPage.jsx
│   ├── SignalsPage.jsx
│   ├── RiskPage.jsx
│   ├── AnalyticsPage.jsx
│   ├── StrategyPage.jsx
│   ├── PaperTradingPage.jsx
│   ├── AutonomousTradingPage.jsx
│   ├── WatchlistPage.jsx   ← new
│   ├── AlertsPage.jsx      ← new
│   ├── TokenManagerPage.jsx
│   ├── WorkflowPage.jsx
│   ├── NotificationsPage.jsx
│   ├── SettingsPage.jsx
│   └── SubscriptionPage.jsx
│
└── store/
    └── index.js            — Zustand: portfolioNAV, portfolioPnL, signals, connected, emergencyStop
```

### 5.2 State Management

**Two-layer state management:**

| Layer | Tool | Scope |
|---|---|---|
| Server state (async) | TanStack React Query | API data, caching, refetching |
| WebSocket / UI state | Zustand | Real-time signals, portfolio NAV, WS connection status |
| Auth state | React Context (AuthContext) | JWT token, user object, logout |

**`AuthContext` tokenRef pattern:**
```js
const tokenRef = useRef(token)
useEffect(() => { tokenRef.current = token }, [token])
// API calls use tokenRef.current instead of closure-captured token
// This avoids stale closures in long-lived callbacks
```

### 5.3 Page & Component Catalogue

| Page | Route | Key Features |
|---|---|---|
| Dashboard | `/dashboard` | Stats cards, BTC price, recent signals, exchange status |
| Portfolio | `/portfolio` | Open positions, P&L summary, TOTAL footer |
| Crypto | `/crypto` | Live candlestick chart, RSI, MACD, order form |
| Watchlist | `/watchlist` | Symbol list, notes, target prices, add/remove ← **new** |
| AI Signals | `/signals` | Signal feed, confidence, entry/stop/target levels |
| Paper Trade | `/paper-trading` | Simulated order entry, virtual P&L |
| Auto Trade | `/autonomous` | Strategy session control, live logs |
| Strategy | `/strategy` | Strategy builder, backtesting |
| Analytics | `/analytics` | Trade history, P&L charts, strategy performance |
| Risk | `/risk` | Risk status, CVaR, Kelly fraction, emergency stop |
| Price Alerts | `/alerts` | Create/manage threshold alerts ← **new** |
| Tokens | `/tokens` | Exchange API key management |
| Workflows | `/workflows` | Automation workflow builder |
| Notifications | `/notifications` | Telegram/Email/WhatsApp channel setup |
| Settings | `/settings` | User preferences, timezone, 2FA |
| Plans | `/subscription` | Free/Pro/Team/Enterprise comparison |
| Admin | `/admin` | User management, audit logs (admin only) |

---

## 6. Real-Time Communication

**WebSocket endpoint:** `wss://domain/ws`

The `ConnectionManager` in `app.py` maintains an in-memory list of active WebSocket connections and provides fan-out broadcasting.

**Event types pushed from server → client:**

| Event | Trigger | Payload |
|---|---|---|
| `portfolio_update` | Trade executed, position change | `{nav, pnl, positions}` |
| `signal` | New AI signal generated | `{symbol, direction, confidence, ...}` |
| `risk_alert` | Emergency stop triggered | `{reason, timestamp}` |
| `price_tick` | Binance WebSocket price update | `{symbol, price, change_pct}` |
| `ei_update` | EI engine state change | `{fear_greed, regime}` |

**Frontend socket hook** (`useAlchemySocket.jsx`):
```
connect → authenticate (send JWT in first message) → subscribe to topics
         ↓
receive message → dispatch to Zustand store by event type
```

---

## 7. Exchange Integrations

```
alchemy/integrations/
├── binance/
│   └── gateway.py     — Binance REST + WebSocket (spot + futures USDM)
├── delta/
│   └── gateway.py     — Delta Exchange REST (crypto derivatives)
├── angel_broking/
│   └── gateway.py     — Angel Broking Smart API (Indian equities)
└── zerodha/
    └── kite_gateway.py — Zerodha Kite Connect (Indian equities/F&O)
```

**Credential storage pattern:**
```
User submits API key + secret
  → AES-256-GCM encrypt with ALCHEMY_VAULT_KEY
  → Store ciphertext in exchange_tokens table
  → On use: decrypt in-memory, never log plaintext
```

**Paper trading fallback:**
All gateways support `paper_trading=True` mode which routes orders to an internal simulator instead of the exchange, returning realistic simulated fills.

---

## 8. Risk & Analytics Pipeline

### 8.1 Pre-Trade Risk Checks

Every order, whether from autonomous trading or manual execution, passes through the `RiskManager` before reaching any exchange:

```
Signal → RiskManager.check(signal)
  ├─ Is emergency stop active? → VETO
  ├─ Daily loss > max_daily_loss_usd? → VETO
  ├─ Open positions >= max_open_positions? → VETO
  ├─ Portfolio drawdown > max_drawdown_pct? → VETO
  ├─ Symbol in blocked_tickers? → VETO
  ├─ Extreme volatility (>3σ)? → VETO (new longs)
  └─ All checks pass → adjust position size + APPROVE
```

### 8.2 CVaR / Expected Shortfall

**Module:** `alchemy/risk/cvar.py`

CVaR (Conditional Value-at-Risk) is the average loss in the worst (1-confidence)% of scenarios. It is a **coherent risk measure** — unlike VaR, it is sub-additive (portfolio CVaR ≤ sum of component CVaRs).

```python
# Example usage
from alchemy.risk.cvar import expected_shortfall

returns = [0.01, -0.02, 0.03, -0.05, ...]  # daily P&L fractions
result = expected_shortfall(returns, confidence=0.95)
# result.var   = 95th percentile loss
# result.cvar  = average loss beyond the 95th percentile
```

The `/api/risk/status` endpoint enriches its response with CVaR computed from the user's last 100 trades:

```json
{
  "emergency_stop": false,
  "daily_pnl": -250.0,
  "cvar_95": 3.42,         // 95% CVaR as % of capital
  "var_95": 2.18,          // 95% VaR as % of capital
  "kelly_fraction": 12.5,  // Quarter-Kelly recommended position size %
  "worst_loss_pct": 8.7    // Single worst trade
}
```

### 8.3 Kelly Criterion Position Sizing

Quarter-Kelly is used to avoid the over-betting instability of full Kelly:

```
full_kelly = edge / avg_win
quarter_kelly = 0.25 × full_kelly

Where: edge = win_rate × avg_win − loss_rate × avg_loss
```

Quarter-Kelly provides ~56% of full Kelly returns with dramatically reduced drawdowns, standard in production quant systems.

---

## 9. Watchlist & Alerts System

### Watchlist (`alchemy/api/watchlist_routes.py`)

- Per-user symbol list stored in `watchlist_items` SQLite table
- Supports optional notes and target price per symbol
- Frontend: `/watchlist` page with add/remove/edit UI
- Upsert semantics: adding a duplicate symbol updates its metadata

### Price Alerts (`alchemy/api/alert_routes.py`)

- Users define `above` or `below` threshold alerts for any symbol/exchange
- Alert states: `active → triggered → (reset to active)` or `disabled`
- Evaluation via `POST /api/alerts/check` with a `{prices: {SYMBOL: price}}` map
- Frontend: `/alerts` page with status filters and create/delete/toggle UI
- Triggered alerts retain their `triggered_at` timestamp for history

---

## 10. Paper Trading

**Module:** `alchemy/paper_trading/`

The paper trading engine simulates live exchange behaviour:

- Market orders: filled at current mid-price ±0.05% slippage
- Limit orders: queued, filled when price crosses level
- Realistic commission simulation (Binance maker/taker fees)
- Virtual portfolio NAV updated on every fill
- P&L stored to analytics DB for strategy backtesting

**API:** `POST /api/paper/order`, `GET /api/paper/positions`, `GET /api/paper/history`

---

## 11. Deployment Architecture

### 11.1 Docker Compose Stack

```yaml
services:
  alchemy:       # FastAPI + React SPA (port 8000)
  nginx:         # Reverse proxy + TLS termination (ports 80/443)
  prometheus:    # Metrics scraper (port 9090)
  grafana:       # Metrics dashboard (port 3000)
  alertmanager:  # Alert routing to Telegram (port 9093)

volumes:
  alchemy_data:  # Persistent DB at /data/alchemy.db (mapped to /var/lib/alchemy)
```

**Critical:** Container runs as `user: "0:0"` to ensure write access to the Docker volume. The `/data` directory is created with `chmod 777` at startup.

### 11.2 Kubernetes (Production)

Manifests in `infra/k8s/`:

```
namespace.yaml       — alchemy namespace
pvc.yaml             — PersistentVolumeClaim for DB
deployment.yaml      — Deployment (2 replicas, rolling update)
service.yaml         — ClusterIP service
ingress.yaml         — Nginx Ingress with TLS (cert-manager)
hpa.yaml             — HorizontalPodAutoscaler (2-10 pods, 70% CPU)
```

### 11.3 CI/CD Pipeline

**GitHub Actions** (`.github/workflows/`):

```
push to main
  → lint (ruff + eslint)
  → test (pytest unit tests)
  → build Docker image
  → push to GitHub Container Registry
  → deploy to VPS via SSH (alchemy-update command)
```

**Zero-downtime deployment:**
```bash
alchemy-update  # alias for:
  docker compose pull &&
  docker compose up -d --remove-orphans &&
  docker compose exec alchemy python -m alchemy.scripts.health_check
```

---

## 12. Observability & Monitoring

### Prometheus Metrics (`/metrics`)

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Request count by method, path, status |
| `http_request_duration_seconds` | Histogram | Latency percentiles |
| `ws_connections_active` | Gauge | Open WebSocket connections |
| `trades_executed_total` | Counter | Trades by exchange and strategy |
| `risk_vetoes_total` | Counter | Risk manager vetoes by reason |

### Grafana Dashboards

Pre-built dashboards at `infra/grafana/`:
- **Alchemy Overview** — request rate, latency, error rate
- **Trading Activity** — trade count, P&L, strategy breakdown
- **Risk Dashboard** — emergency stops, vetoes, drawdown

### Alertmanager Rules

Critical alerts sent to Telegram channel:
- API error rate > 5% for 2 minutes
- Emergency stop triggered
- Daily loss > 80% of limit
- Container restart detected

### Structured Logging

All backend modules use `structlog` with JSON output:
```python
log = structlog.get_logger(__name__)
log.info("trade.executed", symbol="BTCUSDT", side="BUY", price=65000)
```

---

## 13. Security Architecture

### Defence-in-Depth Layers

```
Internet
  │
  ├─ UFW firewall (ports 22, 80, 443 only)
  ├─ Fail2ban (SSH brute force)
  │
  └─ Nginx
       ├─ TLS 1.2+ with strong ciphers
       ├─ Rate limiting (50 req/s per IP)
       │
       └─ FastAPI
            ├─ SecurityHeadersMiddleware
            │   ├─ Content-Security-Policy
            │   ├─ Strict-Transport-Security
            │   ├─ X-Frame-Options: DENY
            │   └─ X-Content-Type-Options: nosniff
            ├─ CORSMiddleware (strict origin allowlist in production)
            ├─ JWT validation on every protected endpoint
            ├─ RBAC (super_admin > admin > trader > analyst > viewer)
            └─ AES-256-GCM vault for exchange credentials
```

### Threat Model

| Threat | Mitigation |
|---|---|
| Credential stuffing | 20-attempt IP block + structlog alert |
| Session hijacking | Short JWT TTL (15min) + refresh token rotation |
| SQL injection | SQLAlchemy ORM parameterised queries throughout |
| XSS | CSP headers + React DOM escaping |
| SSRF | YouTube URL allowlist in `intelligence_routes.py` |
| Secret leak | Credentials never logged; vault encrypted at rest |
| Privilege escalation | RBAC `has_permission()` checked on every admin endpoint |
| Mass assignment | Pydantic schemas whitelist allowed fields on all inputs |

---

## 14. Data Flow Diagrams

### 14.1 Login Flow

```
User → POST /api/auth/login {email, password}
  → RateLimiter check (IP-based)
  → AuthService.authenticate()
  → bcrypt.verify(password, hash)
  → Check user.status (active/pending/locked)
  → Issue JWT (access 15min + refresh 7d)
  → Store refresh_token_hash in user_sessions
  → Return {access_token, refresh_token, user}
  ← 200 OK
```

### 14.2 Order Execution Flow

```
User → POST /api/crypto/execute {symbol, side, size, exchange}
  → JWT validation → get CurrentUser
  → Decrypt exchange credentials from vault
  → Build TradingSignal
  → RiskManager.check(signal)
    ├─ VaR/CVaR within limits?
    ├─ Position limits not exceeded?
    ├─ Emergency stop not active?
    └─ Price guard (sanity check)
  → APPROVED: route to ExchangeGateway
  → ExchangeGateway.place_order()
  → Record to analytics_db (trade record)
  → Broadcast "portfolio_update" via WebSocket
  ← 200 {order_id, fill_price, status}
```

### 14.3 WebSocket Data Flow

```
Client → WS connect → send {token: "JWT"}
Server → validate JWT → add to ConnectionManager.active

Background tasks push to ConnectionManager.broadcast():
  ├─ Binance price ticks → "price_tick" events
  ├─ EI engine updates → "ei_update" events
  ├─ Strategy engine signals → "signal" events
  └─ Risk alerts → "risk_alert" events

Client receives → dispatch to Zustand store
  → React components re-render reactively
```

---

## 15. Module Dependency Map

```
alchemy/
├── api/app.py              depends on: ALL routers, auth.middleware, metrics
├── api/*_routes.py         depends on: auth.middleware, core.config, specific business modules
│
├── auth/
│   ├── middleware.py       depends on: auth.security, core.config
│   ├── security.py         depends on: core.config
│   ├── feature_gate.py     depends on: (standalone)
│   └── service.py          depends on: users.models, auth.security
│
├── core/
│   ├── config.py           depends on: pydantic-settings (no internal deps)
│   ├── state.py            depends on: pydantic
│   └── messages.py         depends on: (standalone)
│
├── users/models.py         depends on: sqlalchemy
│
├── risk/
│   ├── manager.py          depends on: core.config, core.state
│   ├── cvar.py             depends on: (standalone, stdlib only)  ← new
│   └── kill_switch.py      depends on: risk.manager
│
├── intelligence/
│   ├── emotion/ei_engine.py  depends on: analytics_db.store
│   └── crawlers/             depends on: llm, analytics_db
│
├── notifications/dispatcher.py  depends on: notifications.models, providers.*
│
└── analytics_db/store.py   depends on: core.config (standalone SQLite)
```

**Key design principle:** `alchemy/risk/cvar.py`, `alchemy/core/messages.py`, and `alchemy/auth/feature_gate.py` have **zero internal dependencies** — they are purely computational and can be tested in complete isolation.

---

## 16. Configuration Reference

All configuration is via environment variables (`.env.local` for dev, `.env.production` for prod):

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | ✅ prod | — | ≥40 chars, used for all JWT signing |
| `ALCHEMY_VAULT_KEY` | ✅ prod | — | ≥40 chars, AES-256-GCM key for credential vault |
| `DATABASE_URL` | ✅ prod | SQLite | SQLAlchemy async DB URL |
| `ADMIN_EMAIL` | ✅ | — | Bootstrap admin email |
| `ADMIN_PASSWORD` | ✅ | — | Must satisfy PasswordPolicy (upper+lower+digit+special) |
| `ENV` | ✅ | `development` | `production` enables strict security checks |
| `ALLOWED_ORIGINS` | prod | * | Comma-separated CORS origin allowlist |
| `SMTP_HOST` | optional | — | Gmail SMTP host for email OTP |
| `SMTP_USER` | optional | — | Gmail address |
| `SMTP_PASSWORD` | optional | — | 16-char Gmail App Password |
| `LLM_ANTHROPIC_API_KEY` | optional | — | Claude API key for AI features |
| `LLM_OPENAI_API_KEY` | optional | — | GPT API key |
| `DOMAIN` | optional | localhost | Used in Telegram alert URLs |

---

## 17. API Reference Summary

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Email + password → JWT |
| POST | `/api/auth/signup` | Create account |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/logout` | Invalidate session |
| POST | `/api/auth/forgot-password` | Send reset email |
| POST | `/api/auth/reset-password` | Set new password with token |
| POST | `/api/auth/otp/send` | Send email OTP |
| POST | `/api/auth/otp/2fa/setup/init` | TOTP QR code |

### Trading & Market Data

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/crypto/market/btc-price` | Current BTC price |
| GET | `/api/crypto/binance/klines/{symbol}` | OHLCV candlestick data |
| POST | `/api/crypto/execute` | Execute trade |
| GET | `/api/paper/positions` | Paper trading positions |
| POST | `/api/paper/order` | Place paper trade order |

### Intelligence & AI

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/intelligence/signals` | Latest market signals |
| GET | `/api/intelligence/emotional-state` | Fear & Greed index |
| POST | `/api/intelligence/strategies/generate` | Generate trade ideas |
| GET | `/api/intelligence/analytics/pnl-summary` | User P&L summary |

### Risk

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/risk/status` | Risk status + CVaR metrics |
| POST | `/api/risk/emergency-stop` | Trigger kill switch |
| DELETE | `/api/risk/emergency-stop` | Clear emergency stop |

### Watchlist ← new

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/watchlist` | List user's watchlist |
| POST | `/api/watchlist` | Add symbol |
| PATCH | `/api/watchlist/{symbol}` | Update notes/target |
| DELETE | `/api/watchlist/{symbol}` | Remove symbol |
| DELETE | `/api/watchlist` | Clear all |

### Price Alerts ← new

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/alerts` | List alerts (optional `?status_filter=active`) |
| POST | `/api/alerts` | Create alert |
| PATCH | `/api/alerts/{id}` | Update condition/target/status |
| DELETE | `/api/alerts/{id}` | Delete alert |
| POST | `/api/alerts/check` | Evaluate alerts against current prices |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/users` | List all users |
| DELETE | `/api/admin/users/{id}` | Delete user (cascade) |
| PATCH | `/api/admin/users/{id}/subscription` | Change plan |
| GET | `/api/admin/audit-logs` | Audit log |

---

## 18. Known Constraints & Decisions

| Constraint | Reason / Decision |
|---|---|
| WebSocket routes before StaticFiles | Starlette assertion: `scope["type"] == "http"` |
| SQLite in dev, PostgreSQL in prod | Simplicity locally, TimescaleDB for time-series at scale |
| `ChartCanvas` defined outside `LiveChart` | React.memo requires stable identity; inner definitions remount every render |
| tokenRef in AuthContext | Avoid stale closures in WebSocket callbacks |
| No `pattern=` attribute on username input | Chrome v-flag bug with `-` in character classes |
| Quarter-Kelly (0.25×) for position sizing | Full Kelly causes extreme drawdowns under estimation error |
| AES-256-GCM for credential vault | AEAD provides both confidentiality and integrity |
| CVaR at 95% confidence | Basel III standard; more robust than VaR under fat-tailed distributions |
| Raw sqlite3 for watchlist/alerts | Avoids async complexity for simple CRUD; consistent with token_routes pattern |
| Rate limit dev bypass for 127.0.0.1 | Prevents lockout during local development |
| `user: "0:0"` in docker-compose | Ensures write access to Docker volume (was causing read-only DB errors) |

---

## 19. API Gateway Architecture (v0.9.0+)

> Full specification: [`docs/API_GATEWAY_MICROSERVICES.md`](API_GATEWAY_MICROSERVICES.md)

### Gateway Position in the Stack

```
Internet
    │ :443 HTTPS / WSS
    ▼
Nginx (TLS termination, DDoS limits, HSTS)
    │ :8443 internal
    ▼
Kong API Gateway  ← NEW in v0.9.5
    │  JWT verify · Rate limit per plan · Cache market data
    │  Route by /api/v1/{service}/ · Canary · mTLS (internal)
    ▼
FastAPI microservices (or monolith during transition)
```

### Kong Plugins in Use

| Plugin | Purpose |
|---|---|
| `jwt` | Verify RS256 token without a DB call per request |
| `rate-limiting` | Redis-backed, per-consumer, plan-aware limits |
| `proxy-cache` | Cache market data GET responses (2s TTL) |
| `cors` | Replace FastAPI `CORSMiddleware` |
| `ip-restriction` | Block non-admin IPs from `/api/v1/admin/**` |
| `response-transformer` | Add `X-API-Version`, `X-Powered-By` headers |
| `canary` | Route % of traffic to v2 for gradual rollouts |
| `file-log` | Forward access logs to Promtail → Loki |
| `opentelemetry` | Inject `traceparent` for distributed tracing |

---

## 20. Microservices Architecture (v1.0.0)

> Full specification with end-to-end flows: [`docs/API_GATEWAY_MICROSERVICES.md`](API_GATEWAY_MICROSERVICES.md)

### Service Map

| Service | Port | Source modules | Database |
|---|---|---|---|
| Auth Service | 8001 | `alchemy/auth/`, `alchemy/users/` | `alchemy_auth` (PostgreSQL) |
| Trading Service | 8002 | `alchemy/trading/`, `alchemy/execution/`, `alchemy/paper_trading/` | `alchemy_trading` (PostgreSQL) |
| Risk Service | 8003 | `alchemy/risk/` | Redis (kill switch), PostgreSQL (trades) |
| Market Data Service | 8004 | `alchemy/execution/crypto/` | Redis (cache), PostgreSQL (history) |
| Intelligence Service | 8005 | `alchemy/intelligence/`, `alchemy/agents/` | ChromaDB, PostgreSQL |
| Notification Service | 8006 | `alchemy/notifications/` | `alchemy_notify` (PostgreSQL) |
| Admin Service | 8007 | `alchemy/admin/` | Read replicas |
| WebSocket Hub | 8008 | `alchemy/api/app.py` (ConnectionManager) | Redis pub/sub |

### Inter-Service Communication

- **Synchronous** — gRPC for latency-critical calls (Trading → Risk pre-trade check: <50ms)
- **Asynchronous** — Redis Streams for fire-and-forget (order fills → notifications → analytics)
- **Pub/Sub** — Redis channels for real-time fan-out (market prices → WS Hub → clients)

---

## 21. Mobile Communication Architecture (v0.9.0+)

### Communication Protocols

| Protocol | Use case | Transport |
|---|---|---|
| REST (HTTPS) | All CRUD operations, trading, auth | HTTPS/2 |
| WebSocket (WSS) | Real-time prices, signals, alerts | WSS |
| Push (FCM/APNS) | Background alerts, order fills | FCM / APNs HTTP/2 |
| SSE | Fallback when WS blocked by corporate proxy | HTTPS SSE |

### Mobile-Specific API Features (v0.9.0)

- `?since=<unix_ts>` — Delta sync: only return records changed after timestamp
- `?fields=price,symbol` — Sparse fieldsets: reduce payload size for slow networks
- `POST /api/v1/push/register` — Register FCM/APNS device token
- `POST /api/v1/auth/refresh` — Rotate refresh token (30-day TTL for mobile)
- `POST /api/v1/auth/revoke` — Revoke token on logout or app uninstall

### Push Notification Events

| Event | Trigger | Deep link |
|---|---|---|
| `price_alert_triggered` | Threshold price crossed | `/alerts/{id}` |
| `order_filled` | Exchange confirms fill | `/portfolio` |
| `kill_switch_activated` | Emergency stop activated | `/risk` |
| `ai_signal` | New strong AI signal generated | `/signals` |
| `daily_pnl_milestone` | Daily P&L target reached | `/analytics` |

---

*This document is auto-maintained alongside the codebase.*  
*For questions, see [CLAUDE.md](../CLAUDE.md) for AI assistant context or [DEPLOYMENT.md](../DEPLOYMENT.md) for ops procedures.*  
*For API Gateway + microservices: [`docs/API_GATEWAY_MICROSERVICES.md`](API_GATEWAY_MICROSERVICES.md)*  
*For versioned roadmap + all recommendations: [`docs/PLATFORM_EVOLUTION.md`](PLATFORM_EVOLUTION.md)*
