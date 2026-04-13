# Alchemy — API Gateway & Microservices Architecture
## Web and Mobile Communication Reference

**Application:** Alchemy AI Trading Platform  
**Production:** https://akilamirthya.in  
**Document Version:** 0.9.0 · April 2026  
**Status:** Approved for Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State vs Target State](#2-current-state-vs-target-state)
3. [API Gateway Architecture](#3-api-gateway-architecture)
   - 3.1 [Gateway Selection Rationale](#31-gateway-selection-rationale)
   - 3.2 [Gateway Topology](#32-gateway-topology)
   - 3.3 [Gateway Capabilities](#33-gateway-capabilities)
   - 3.4 [Kong Declarative Configuration](#34-kong-declarative-configuration)
4. [Microservices Decomposition](#4-microservices-decomposition)
   - 4.1 [Service Boundary Map](#41-service-boundary-map)
   - 4.2 [Auth Service](#42-auth-service)
   - 4.3 [Trading Service](#43-trading-service)
   - 4.4 [Market Data Service](#44-market-data-service)
   - 4.5 [Intelligence Service](#45-intelligence-service)
   - 4.6 [Risk Service](#46-risk-service)
   - 4.7 [Notification Service](#47-notification-service)
   - 4.8 [Admin Service](#48-admin-service)
   - 4.9 [WebSocket Hub](#49-websocket-hub)
5. [Web Communication Patterns](#5-web-communication-patterns)
   - 5.1 [REST API (HTTPS)](#51-rest-api-https)
   - 5.2 [Real-Time WebSocket (WSS)](#52-real-time-websocket-wss)
   - 5.3 [Server-Sent Events (SSE)](#53-server-sent-events-sse)
6. [Mobile Communication Patterns](#6-mobile-communication-patterns)
   - 6.1 [Mobile-First API Design](#61-mobile-first-api-design)
   - 6.2 [Push Notifications (FCM / APNS)](#62-push-notifications-fcm--apns)
   - 6.3 [Offline-First Sync](#63-offline-first-sync)
   - 6.4 [Refresh Token Rotation](#64-refresh-token-rotation)
7. [Inter-Service Communication](#7-inter-service-communication)
   - 7.1 [Synchronous (gRPC)](#71-synchronous-grpc)
   - 7.2 [Asynchronous (Redis Streams)](#72-asynchronous-redis-streams)
8. [End-to-End Flow Diagrams](#8-end-to-end-flow-diagrams)
   - 8.1 [Login Flow (Web + Mobile)](#81-login-flow-web--mobile)
   - 8.2 [Live Trade Execution Flow](#82-live-trade-execution-flow)
   - 8.3 [Price Alert → Push Notification Flow](#83-price-alert--push-notification-flow)
   - 8.4 [AI Signal Generation Flow](#84-ai-signal-generation-flow)
   - 8.5 [Market Data Real-Time Flow](#85-market-data-real-time-flow)
9. [Data Store Strategy](#9-data-store-strategy)
10. [Security at the Gateway](#10-security-at-the-gateway)
11. [Rate Limiting Strategy](#11-rate-limiting-strategy)
12. [Observability](#12-observability)
13. [Docker Compose (Target)](#13-docker-compose-target)
14. [Kubernetes Helm Overview](#14-kubernetes-helm-overview)
15. [Migration Checklist](#15-migration-checklist)

---

## 1. Executive Summary

Alchemy currently runs as a **single FastAPI monolith** behind Nginx. This works well up to ~500 concurrent users. Beyond that, the architecture hits three hard limits:

| Constraint | Impact | Threshold |
|---|---|---|
| SQLite serialised writes | Order execution queue backs up | >50 concurrent traders |
| In-memory WebSocket manager | Cannot scale to >1 process | >1 worker |
| In-memory rate limiter | Resets on deploy, not shared | >1 container |

The target architecture introduces:
- **Kong API Gateway** as the single entry point for all clients (web browser, React Native mobile app, third-party bots)
- **8 microservices** extracted from the existing monolith, matching its existing module boundaries
- **Redis** as the shared backbone for pub/sub, rate limiting, and caching
- **PostgreSQL** replacing SQLite for the primary database

The migration is **additive and incremental** — the monolith keeps running while services are extracted one at a time.

---

## 2. Current State vs Target State

### Current State (v0.8.0)

```
Browser ──HTTPS──▶ Nginx ──HTTP──▶ FastAPI monolith (single process)
                                         │
                              ┌──────────┴──────────┐
                          SQLite DB          In-memory state
                          (one file)         (rate limiter,
                                              WS manager)
```

**Limitations:**
- Single point of failure
- Cannot run multiple workers (in-memory WS + rate limiter)
- SQLite blocks concurrent writes
- No mobile push notifications
- No API versioning

### Target State (v1.0.0)

```
Browser  ──WSS/HTTPS──▶ ┌─────────────────────────────┐
Mobile   ──WSS/HTTPS──▶ │      Kong API Gateway        │
3rd-party Bot ──HTTP──▶ │  JWT verify · Rate limit      │
                        │  Route · Cache · Canary       │
                        └──────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────────────┐
              │                    │                            │
         /api/v1/auth        /api/v1/trading            /api/v1/market
              │                    │                            │
        ┌─────▼──────┐    ┌────────▼───────┐    ┌─────────────▼──────┐
        │ Auth Svc   │    │ Trading Svc    │    │ Market Data Svc    │
        │ :8001      │    │ :8002          │    │ :8004              │
        └────────────┘    └────────────────┘    └────────────────────┘
              │                    │                            │
        ┌─────▼──────┐    ┌────────▼───────┐                   │
        │ Risk Svc   │    │ Intelligence   │              Redis pub/sub
        │ :8003      │    │ Svc :8005      │                   │
        └────────────┘    └────────────────┘    ┌──────────────▼──────┐
                                                │  WebSocket Hub      │
        ┌────────────┐    ┌────────────────┐    │  :8008              │
        │ Notify Svc │    │ Admin Svc      │    └─────────────────────┘
        │ :8006      │    │ :8007          │
        └────────────┘    └────────────────┘
              │
        ┌─────▼──────────────────────────────────────────────────────┐
        │                     Shared Infrastructure                   │
        │  PostgreSQL :5432  │  Redis :6379  │  Prometheus :9090      │
        └────────────────────────────────────────────────────────────┘
```

---

## 3. API Gateway Architecture

### 3.1 Gateway Selection Rationale

| Gateway | Pros | Cons | Verdict |
|---|---|---|---|
| **Kong OSS** | Plugin ecosystem, admin API, DB-less mode, WebSocket passthrough, K8s ingress controller | Slightly heavier runtime | ✅ **Recommended** |
| Traefik | Excellent K8s integration, zero-config service discovery | Fewer auth plugins, complex rate limiting | ✅ Good K8s option |
| AWS API Gateway | Managed, scales automatically | Vendor lock-in, latency, cost at volume | For cloud-native path only |
| Nginx (current) | Already in use, simple | No plugin ecosystem, no admin API, no JWT introspection | Keep as edge proxy only |

**Decision:** Kong OSS in DB-less mode (declarative YAML config), deployed as a container alongside the existing Nginx which becomes a TLS terminator only.

### 3.2 Gateway Topology

```
Internet
    │
    ▼ :443 (TLS)
┌──────────────────────────────────────────────────────────────────┐
│                    Nginx  (TLS termination only)                  │
│  SSL offload · HSTS · Certbot renewal · DDoS connection limits   │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ :8443 (internal HTTPS)
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Kong API Gateway                             │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ JWT Plugin   │  │ Rate Limit   │  │ Response Transformer    │ │
│  │ Verify token │  │ Per consumer │  │ Add CORS / API-version  │ │
│  │ No DB calls  │  │ plan-aware   │  │ headers                 │ │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘ │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ Proxy Cache  │  │ Canary       │  │ Request Validator       │ │
│  │ Market data  │  │ v1→v2 split  │  │ Schema enforcement      │ │
│  │ 2s TTL       │  │ (% traffic)  │  │ Reject bad payloads     │ │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘ │
│                                                                   │
│  Routes:                                                          │
│   /api/v1/auth/**    → http://auth-svc:8001                      │
│   /api/v1/trading/** → http://trading-svc:8002                   │
│   /api/v1/risk/**    → http://risk-svc:8003                      │
│   /api/v1/market/**  → http://market-svc:8004                    │
│   /api/v1/ai/**      → http://intelligence-svc:8005              │
│   /api/v1/alerts/**  → http://notification-svc:8006              │
│   /api/v1/admin/**   → http://admin-svc:8007                     │
│   /ws                → http://ws-hub:8008 (WebSocket upgrade)    │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 Gateway Capabilities

| Capability | Implementation | Plan Tier |
|---|---|---|
| **JWT verification** | Kong JWT plugin (RS256 / HS256) | All |
| **Rate limiting** | Kong Rate Limiting Advanced (Redis backend) | Per plan |
| **Request caching** | Kong Proxy Cache (market data, 2–5s TTL) | All |
| **API versioning** | Route prefix `/api/v1/`, `/api/v2/` | All |
| **Canary releases** | Kong Canary plugin (% traffic split) | Deployments |
| **IP allowlist** | Kong IP Restriction (admin routes) | Admin |
| **CORS** | Kong CORS plugin (replaces FastAPI middleware) | All |
| **mTLS** | Kong mTLS plugin (inter-service) | Internal |
| **WebSocket** | Native passthrough via Kong's `protocols: ["http","https","ws","wss"]` | All |
| **Logging** | Kong File Log → Promtail → Loki | All |
| **Schema validation** | Kong Request Validator | API |

### 3.4 Kong Declarative Configuration

```yaml
# deploy/kong.yml
_format_version: "3.0"

services:
  - name: auth-service
    url: http://auth-svc:8001
    routes:
      - name: auth-routes
        paths: ["/api/v1/auth"]
        methods: ["GET","POST","PUT","DELETE","PATCH","OPTIONS"]
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 10
          policy: redis
          redis_host: redis
          redis_port: 6379

  - name: trading-service
    url: http://trading-svc:8002
    routes:
      - name: trading-routes
        paths: ["/api/v1/trading", "/api/v1/paper", "/api/v1/crypto"]
        strip_path: false
    plugins:
      - name: jwt
        config:
          secret_is_base64: false
      - name: rate-limiting
        config:
          minute: 100
          policy: redis
          redis_host: redis

  - name: market-data-service
    url: http://market-svc:8004
    routes:
      - name: market-routes
        paths: ["/api/v1/market"]
        strip_path: false
    plugins:
      - name: proxy-cache
        config:
          response_code: [200]
          request_method: ["GET"]
          content_type: ["application/json"]
          cache_ttl: 2         # 2 second TTL for live price data
          strategy: memory

  - name: ws-hub
    url: http://ws-hub:8008
    routes:
      - name: websocket-route
        paths: ["/ws"]
        protocols: ["http","https","ws","wss"]
        strip_path: false

# Global plugins
plugins:
  - name: cors
    config:
      origins: ["https://akilamirthya.in", "https://app.akilamirthya.in"]
      methods: ["GET","POST","PUT","DELETE","PATCH","OPTIONS"]
      headers: ["Authorization","Content-Type","X-Request-ID"]
      exposed_headers: ["X-RateLimit-Remaining","X-RateLimit-Reset"]
      max_age: 3600
      credentials: true

  - name: response-transformer
    config:
      add:
        headers:
          - "X-API-Version: v1"
          - "X-Powered-By: Alchemy"
```

---

## 4. Microservices Decomposition

### 4.1 Service Boundary Map

Each service maps to an existing directory in the monolith. No new business logic — just physical separation.

```
alchemy/ (monolith)
├── auth/           → Auth Service (8001)
├── users/          → Auth Service (8001)
├── trading/        → Trading Service (8002)
├── execution/      → Trading Service (8002)
├── paper_trading/  → Trading Service (8002)
├── risk/           → Risk Service (8003)
├── integrations/   → Market Data Service (8004)
├── intelligence/   → Intelligence Service (8005)
├── agents/         → Intelligence Service (8005)
├── notifications/  → Notification Service (8006)
├── admin/          → Admin Service (8007)
└── analytics/      → shared lib (imported by Risk + Admin)
```

**Shared libraries** (not services — deployed as a pip-installable package `alchemy-core`):
- `alchemy/core/config.py`
- `alchemy/core/messages.py`
- `alchemy/analytics/`
- `alchemy/users/models.py`

### 4.2 Auth Service

**Port:** 8001  
**Responsibility:** Identity, sessions, OTP, 2FA, password management

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/auth/login` | POST | Email + password → JWT access + refresh token |
| `/api/v1/auth/signup` | POST | Create account |
| `/api/v1/auth/refresh` | POST | Rotate refresh token |
| `/api/v1/auth/revoke` | POST | Revoke refresh token (logout) |
| `/api/v1/auth/password/forgot` | POST | Send reset link |
| `/api/v1/auth/password/reset` | POST | Apply new password via token |
| `/api/v1/auth/otp/send` | POST | Email OTP |
| `/api/v1/auth/otp/verify` | POST | Verify OTP |
| `/api/v1/auth/2fa/init` | POST | TOTP QR code |
| `/api/v1/auth/2fa/confirm` | POST | Activate 2FA |

**Database:** PostgreSQL `alchemy_auth` schema  
**Tables:** `users`, `user_sessions`, `audit_logs`, `otp_store`  
**Cache:** Redis (session blacklist, OTP store with TTL)  

**Key security rules:**
- JWT signed with RS256 (private key in Auth Service, public key distributed to all other services and the gateway)
- Refresh tokens stored hashed (SHA-256) in `user_sessions` with device fingerprint
- OTP codes hashed before storage, 10-minute TTL enforced by Redis key expiry (not application logic)

### 4.3 Trading Service

**Port:** 8002  
**Responsibility:** Order routing, paper trading, autonomous strategy runner, exchange credential management

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/trading/orders` | POST | Place live order |
| `/api/v1/trading/orders/{id}` | GET/DELETE | Get/cancel order |
| `/api/v1/trading/positions` | GET | Open positions |
| `/api/v1/trading/tokens` | GET/POST/DELETE | Exchange API credentials (AES-256-GCM vault) |
| `/api/v1/paper/orders` | POST | Simulated order |
| `/api/v1/paper/portfolio` | GET | Paper portfolio state |
| `/api/v1/trading/autonomous/start` | POST | Start strategy runner |
| `/api/v1/trading/autonomous/stop` | POST | Emergency stop |
| `/api/v1/trading/autonomous/status` | GET | Strategy runner state |

**Database:** PostgreSQL `alchemy_trading` schema  
**Tables:** `exchange_tokens`, `paper_trades`, `orders`  
**Message bus:** Publishes `order.placed`, `order.filled`, `position.opened`, `position.closed` to Redis Streams  
**Upstream calls:** Market Data Service (prices for order validation), Risk Service (pre-trade checks)

### 4.4 Market Data Service

**Port:** 8004  
**Responsibility:** Real-time and historical price data from all exchanges. Only service that connects directly to exchange WebSockets.

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/market/price/{symbol}` | GET | Latest price (cached 2s) |
| `/api/v1/market/candles/{symbol}` | GET | Historical candles |
| `/api/v1/market/orderbook/{symbol}` | GET | Live order book |
| `/api/v1/market/ticker` | GET | Multi-symbol ticker strip |
| `/api/v1/market/exchanges` | GET | Available exchanges + status |

**Caching:** Redis with 2-second TTL for spot prices, 10-second for order books  
**Publishes to:** Redis channel `market:prices` (consumed by WebSocket Hub and Alert Service)  
**No authentication required** for public market data endpoints — enforced at gateway

### 4.5 Intelligence Service

**Port:** 8005  
**Responsibility:** AI signals, Emotional Intelligence (EI), news crawlers, LLM strategy generation

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/ai/signal` | POST | Generate trading signal |
| `/api/v1/ai/strategies` | GET | List strategies |
| `/api/v1/ai/ei/state` | GET | EI Fear & Greed + market regime |
| `/api/v1/ai/features` | GET | User's AI feature entitlements |
| `/api/v1/ai/news` | GET | Latest crawled news headlines |

**Upstream:** LiteLLM gateway (Anthropic/OpenAI/Google)  
**Database:** ChromaDB vector store (semantic market memory)  
**Feature gate:** Checks `subscription` claim from JWT (passed via gateway) before LLM calls

### 4.6 Risk Service

**Port:** 8003  
**Responsibility:** Pre-trade risk checks, CVaR, kill switch, position sizing

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/risk/status` | GET | CVaR, VaR, Kelly fraction, daily P&L |
| `/api/v1/risk/check` | POST | Pre-trade: approve/reject order |
| `/api/v1/risk/kill-switch/activate` | POST | Emergency stop all trading |
| `/api/v1/risk/kill-switch/status` | GET | Kill switch state |
| `/api/v1/risk/capital` | GET/PUT | Capital allocation per strategy |

**Singleton:** `get_risk_manager()` pattern maintained (see `alchemy/risk/manager.py:219-230`)  
**Kill switch** propagates via Redis key `alchemy:kill_switch` so all trading instances see it immediately — no longer dependent on a single-process singleton

### 4.7 Notification Service

**Port:** 8006  
**Responsibility:** Price alerts, push notifications (FCM/APNS), Telegram, email, WhatsApp dispatch

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/alerts` | GET/POST | List/create price alerts |
| `/api/v1/alerts/{id}` | PUT/DELETE | Update/delete alert |
| `/api/v1/alerts/check` | POST | Evaluate alerts against prices |
| `/api/v1/notifications/settings` | GET/PUT | User notification preferences |
| `/api/v1/push/register` | POST | Register device token (FCM/APNS) |
| `/api/v1/push/revoke` | DELETE | Remove device token on logout |

**New:** `push_tokens` table (`user_id`, `device_token`, `platform`, `created_at`, `last_seen_at`)  
**Subscribes to:** Redis channel `market:prices` (evaluate price alerts asynchronously)  
**Subscribes to:** Redis Stream `order.filled` (send order confirmation push)  
**Providers:** Email (SMTP), Telegram Bot, WhatsApp (Twilio), FCM (Firebase), APNS (Apple)

### 4.8 Admin Service

**Port:** 8007  
**Responsibility:** User management, audit logs, subscription management, platform stats

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/admin/users` | GET | List all users |
| `/api/v1/admin/users/{id}` | GET/DELETE | Get/delete user (cascade) |
| `/api/v1/admin/users/{id}/subscription` | PATCH | Change subscription plan |
| `/api/v1/admin/users/{id}/status` | PATCH | Activate/suspend/ban |
| `/api/v1/admin/audit` | GET | Paginated audit log |
| `/api/v1/admin/stats` | GET | DAU, MAU, revenue, exchange usage |

**IP restriction:** Kong IP Restriction plugin limits `/api/v1/admin/**` to internal CIDR only  
**Role check:** Requires `role: admin` or `role: super_admin` in JWT claims

### 4.9 WebSocket Hub

**Port:** 8008  
**Responsibility:** Fan-out real-time events to all connected clients (web + mobile)

**The critical fix from the monolith:** In-memory `ConnectionManager` breaks with multiple workers. The Hub uses Redis pub/sub so any number of Hub replicas can broadcast to all clients.

```
Client (browser/mobile)
    │  WSS /ws
    ▼
WebSocket Hub (8008)
    │  subscribe
    ▼
Redis channel: alchemy:ws:broadcast
    ▲  publish
    │
Market Data Service  ─── publishes price ticks
Trading Service      ─── publishes order fills
Risk Service         ─── publishes kill-switch events
Intelligence Service ─── publishes AI signals
```

**Protocol:** Each message is a JSON envelope:
```json
{
  "event": "price_tick",
  "symbol": "BTCUSDT",
  "exchange": "binance",
  "price": 68420.50,
  "ts": 1713614205.123
}
```

**Supported events:**
| Event | Source | Description |
|---|---|---|
| `price_tick` | Market Data | Real-time price |
| `order_filled` | Trading | Order execution confirmation |
| `position_update` | Trading | Portfolio position change |
| `signal` | Intelligence | New AI trade signal |
| `kill_switch` | Risk | Emergency stop activated |
| `alert_triggered` | Notification | Price alert crossed threshold |
| `portfolio_nav` | Analytics | Portfolio NAV update |

---

## 5. Web Communication Patterns

### 5.1 REST API (HTTPS)

All REST endpoints follow the pattern:
```
https://akilamirthya.in/api/v1/{service}/{resource}
```

**Versioning strategy:**
- URL path versioning: `/api/v1/`, `/api/v2/`
- `Accept-Version` header as fallback for clients that cannot modify URLs
- Old versions sunset after 6 months with deprecation warnings in response headers

**Standard response envelope:**
```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "api_version": "v1",
    "ts": 1713614205
  }
}
```

**Error envelope:**
```json
{
  "error": {
    "code": "plan_upgrade_required",
    "message": "This feature requires the Pro plan.",
    "details": { "current_plan": "free", "required_plan": "pro" }
  },
  "meta": { "request_id": "req_abc123", "ts": 1713614205 }
}
```

**HTTP status codes used:**
| Code | When |
|---|---|
| 200 | Success with body |
| 201 | Resource created |
| 204 | Success, no body (DELETE) |
| 400 | Validation error |
| 401 | Not authenticated |
| 403 | Authenticated but insufficient permission/plan |
| 404 | Resource not found |
| 409 | Conflict (duplicate) |
| 422 | Unprocessable entity (FastAPI validation) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable |

**Caching headers** (added by gateway for GET endpoints):
```
Cache-Control: public, max-age=2, stale-while-revalidate=5
ETag: "a1b2c3d4"
Last-Modified: Mon, 13 Apr 2026 12:00:00 GMT
```

### 5.2 Real-Time WebSocket (WSS)

Connection flow for web clients:
```
1. GET /api/v1/auth/login → { access_token, refresh_token }
2. WSS /ws?token={access_token}
   └─ Gateway verifies JWT before upgrade
   └─ Connection assigned to user's subscription tier
3. Send: { "type": "subscribe", "symbols": ["BTCUSDT","ETHUSDT"] }
4. Receive: stream of { "event": "price_tick", "symbol": ..., "price": ... }
5. On token expiry: close + reconnect with refreshed token
```

**Heartbeat:** Client sends `{ "type": "ping" }` every 30s; Hub replies `{ "type": "pong" }`. No ping for 60s → connection closed.

### 5.3 Server-Sent Events (SSE)

For clients where WebSocket is blocked (corporate proxies), SSE is available as fallback:

```
GET /api/v1/market/stream?symbols=BTCUSDT,ETHUSDT
Authorization: Bearer {token}
Accept: text/event-stream
```

Response stream:
```
data: {"event":"price_tick","symbol":"BTCUSDT","price":68420.50}

data: {"event":"price_tick","symbol":"ETHUSDT","price":3821.10}
```

---

## 6. Mobile Communication Patterns

### 6.1 Mobile-First API Design

Mobile clients require additional considerations beyond the web app:

| Concern | Solution |
|---|---|
| **Bandwidth** | `?fields=price,symbol` sparse fieldset projection |
| **Offline resume** | `?since=<unix_ts>` delta sync on reconnect |
| **Battery** | Exponential backoff on reconnect (1s → 2s → 4s → max 60s) |
| **Slow networks** | Response compression (gzip, already in Nginx) |
| **App updates** | API versioning ensures old mobile builds keep working |
| **Background fetch** | Push instead of polling (see §6.2) |

**Delta sync example:**
```
GET /api/v1/alerts?since=1713614000
→ only alerts created/updated after that timestamp
```

**Sparse fieldset example:**
```
GET /api/v1/market/price/BTCUSDT?fields=price,change_24h
→ { "price": 68420.50, "change_24h": 2.4 }
```

**Mobile-specific headers sent by gateway:**
```
X-Platform: ios | android | web
X-App-Version: 1.2.3
X-Device-ID: {uuid}  (for push token correlation)
```

### 6.2 Push Notifications (FCM / APNS)

Push notifications replace the need for mobile apps to maintain a persistent WebSocket in the background.

**Registration flow:**
```
1. App launches → request push permission
2. OS returns device_token
3. POST /api/v1/push/register
   { "device_token": "...", "platform": "ios" }
4. Server stores in push_tokens table
```

**Delivery flow (price alert example):**
```
Market Data Service
    │ publishes price
    ▼
Redis: market:prices channel
    │ subscribed
    ▼
Notification Service
    │ evaluates price_alerts table
    │ alert threshold crossed
    ▼
FCM / APNS (Firebase Admin SDK / APNs HTTP/2)
    │
    ▼
User's phone: "⚡ BTCUSDT crossed $70,000 ↑"
```

**Push payload structure:**
```json
{
  "notification": {
    "title": "Price Alert Triggered",
    "body": "BTCUSDT crossed ₹70,000 ↑"
  },
  "data": {
    "type": "price_alert",
    "symbol": "BTCUSDT",
    "alert_id": "a1b2c3",
    "deep_link": "/alerts/a1b2c3"
  },
  "apns": {
    "payload": { "aps": { "badge": 1, "sound": "default" } }
  }
}
```

**Push token table:**
```sql
CREATE TABLE push_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_token TEXT NOT NULL UNIQUE,
    platform    VARCHAR(10) NOT NULL CHECK (platform IN ('ios','android')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_push_tokens_user ON push_tokens(user_id);
```

### 6.3 Offline-First Sync

Mobile apps should function with degraded connectivity:

| Data type | Strategy | Sync endpoint |
|---|---|---|
| Watchlist | Cache locally, sync on reconnect | `GET /api/v1/watchlist?since={ts}` |
| Price alerts | Cache locally, push confirms | `GET /api/v1/alerts?since={ts}` |
| Portfolio | Read-only cache, real-time via WS | `GET /api/v1/trading/positions` |
| AI Signals | Cache last 10 signals | `GET /api/v1/ai/signal/history?limit=10` |
| Market prices | Always live — no offline | — |

### 6.4 Refresh Token Rotation

Mobile apps remain logged in for months. The current single access-token JWT (15-minute TTL) forces re-authentication.

**New dual-token flow:**

```
POST /api/v1/auth/login
→ {
    "access_token":  "<JWT, 15min>",
    "refresh_token": "<opaque 256-bit, 30 days>",
    "expires_at":    1713615005
  }

When access_token expires:
POST /api/v1/auth/refresh
  Body: { "refresh_token": "..." }
→ {
    "access_token":  "<new JWT, 15min>",
    "refresh_token": "<NEW opaque token, 30 days>",   ← rotated
    "expires_at":    1713615905
  }

On logout:
POST /api/v1/auth/revoke
  Body: { "refresh_token": "..." }
→ 204 No Content  (token blacklisted in Redis)
```

**Refresh token storage:**
- Mobile: iOS Keychain / Android Keystore (encrypted)
- Web: HttpOnly Secure cookie (never accessible to JS)
- Server: SHA-256 hash stored in `user_sessions` table with `device_id` and `ip_address`

---

## 7. Inter-Service Communication

### 7.1 Synchronous (gRPC)

For latency-critical calls between services where a response is needed before proceeding:

| Caller | Target | Operation | Max Latency |
|---|---|---|---|
| Trading Service | Risk Service | Pre-trade check | 50ms |
| Trading Service | Market Data | Current price | 20ms |
| Intelligence | Market Data | Candle history for signal | 200ms |

**Proto definition (example):**
```protobuf
// risk/risk.proto
service RiskService {
  rpc CheckOrder(OrderCheckRequest) returns (OrderCheckResponse);
  rpc GetKillSwitchStatus(Empty) returns (KillSwitchStatus);
}

message OrderCheckRequest {
  string user_id = 1;
  string symbol = 2;
  string side = 3;
  double quantity = 4;
  double price = 5;
}

message OrderCheckResponse {
  bool approved = 1;
  string reason = 2;
  double position_size_override = 3;
}
```

### 7.2 Asynchronous (Redis Streams)

For fire-and-forget operations where the caller does not wait for a result:

```
Stream name: alchemy:events
Consumer groups: notification-svc, analytics-svc, audit-svc

Event types published to stream:
  order.placed     → { user_id, order_id, symbol, side, qty, price }
  order.filled     → { user_id, order_id, fill_price, fill_qty }
  position.opened  → { user_id, symbol, side, qty, entry_price }
  position.closed  → { user_id, symbol, pnl, exit_price }
  alert.triggered  → { user_id, alert_id, symbol, price }
  kill_switch.activated → { user_id, reason, ts }
  user.registered  → { user_id, email, plan }
  plan.changed     → { user_id, old_plan, new_plan }
```

**Consumer group pattern:**
```python
# Each service reads its own consumer group
await redis.xread(
    {"alchemy:events": last_id},
    count=100,
    block=1000  # ms
)
# Acknowledge after processing
await redis.xack("alchemy:events", "notification-svc", message_id)
```

---

## 8. End-to-End Flow Diagrams

### 8.1 Login Flow (Web + Mobile)

```
Client                 Kong Gateway          Auth Service          PostgreSQL   Redis
  │                        │                     │                    │           │
  │── POST /api/v1/auth/login ──────────────────▶│                    │           │
  │   { email, password }  │                     │                    │           │
  │                        │── Route to Auth ──▶ │                    │           │
  │                        │                     │── SELECT user ────▶│           │
  │                        │                     │◀─ user row ────────│           │
  │                        │                     │── bcrypt.verify()  │           │
  │                        │                     │── INSERT session ─▶│           │
  │                        │                     │── SET refresh hash ├──────────▶│
  │                        │                     │   (SHA-256, TTL 30d)           │
  │                        │                     │── sign JWT (RS256) │           │
  │◀─ 200 { access_token, refresh_token } ───────│                    │           │
  │                        │                     │                    │           │

Client now stores:
  Web:    access_token in memory, refresh_token in HttpOnly cookie
  Mobile: access_token in memory, refresh_token in OS secure storage
```

### 8.2 Live Trade Execution Flow

```
Client          Gateway    Trading Svc    Risk Svc   Market Svc   Exchange
  │                │           │              │           │           │
  │─ POST /api/v1/trading/orders ──────────▶ │           │           │
  │                │           │              │           │           │
  │                │── JWT verify             │           │           │
  │                │── Rate check (plan tier) │           │           │
  │                │────────────────────────▶ │           │           │
  │                │           │── GET price ─────────────────────▶  │
  │                │           │◀─ current price ──────────────────── │
  │                │           │── CheckOrder ─────────▶ │           │
  │                │           │   (qty, price, user_id) │           │
  │                │           │◀─ approved / capped ─── │           │
  │                │           │── AES-decrypt API key   │           │
  │                │           │── exchange.place_order ─────────────▶│
  │                │           │◀─ order_id ─────────────────────────  │
  │                │           │── INSERT order in DB    │           │
  │                │           │── XADD order.placed ────────────────────────▶ Redis
  │◀─ 201 { order_id, status } │              │           │           │
  │                │           │              │           │           │
                               │ [async] Exchange WS sends fill
  │                │           │◀─ fill event from exchange WS                │
  │                │           │── XADD order.filled ───────────────────────▶ Redis
  │                │           │                         │           │
                               ▼ [Redis Stream consumer]
                         Notification Svc ─── push "Order filled: BTC +0.1 @ $68,420"
                         Analytics Svc    ─── record trade in P&L store
                         Audit Svc        ─── write audit_log entry
```

### 8.3 Price Alert → Push Notification Flow

```
Market Data Svc          Redis                  Notification Svc        FCM/APNS
      │                    │                          │                     │
      │── PUBLISH market:prices:BTCUSDT ─────────────▶│                    │
      │   { price: 70050.00 }          │               │                    │
      │                    │           │               │                    │
      │                    │           │── Query active alerts for BTCUSDT  │
      │                    │           │   WHERE threshold <= 70050         │
      │                    │           │── alert found: user_id=abc, threshold=70000 │
      │                    │           │── UPDATE alert SET status='triggered'       │
      │                    │           │── GET push_tokens WHERE user_id=abc         │
      │                    │           │── Send FCM / APNS payload ─────────────────▶│
      │                    │           │                                    │─ deliver to phone
      │                    │           │── XADD alert.triggered ──────────▶ Redis Stream
      │                    │           │── (optionally) send Telegram/email │
```

### 8.4 AI Signal Generation Flow

```
Client          Gateway    Intelligence Svc    Market Data Svc   LiteLLM   WebSocket Hub
  │                │             │                   │              │           │
  │─ POST /api/v1/ai/signal ───▶ │                   │              │           │
  │   { ticker: "BTCUSDT" }      │                   │              │           │
  │                │── check feature: ai.ideas_50 ─▶ │              │           │
  │                │── check daily usage quota       │              │           │
  │                │────────────────────────────────▶│              │           │
  │                │             │── GET candles ────────────────▶  │           │
  │                │             │◀─ last 100 candles ─────────────  │           │
  │                │             │── compute RSI, MACD, BB, EMA     │           │
  │                │             │── GET EI state (Fear & Greed)     │           │
  │                │             │── GET news headlines              │           │
  │                │             │── LLM prompt (context + data) ───────────── ▶│
  │                │             │◀─ structured signal (JSON) ────────────────── │
  │                │             │── PUBLISH alchemy:ws:broadcast ──────────────▶│
  │                │             │   { event: "signal", ... }       │       broadcasts to all WS clients
  │◀─ 200 { signal } ───────────▶│                   │              │           │
```

### 8.5 Market Data Real-Time Flow

```
Binance WS          Market Data Svc        Redis           WebSocket Hub     Client
    │                     │                  │                   │               │
    │─ BTC price tick ───▶│                  │                   │               │
    │                     │── SET market:price:BTCUSDT ─────────▶│               │
    │                     │   (TTL 2s)       │                   │               │
    │                     │── PUBLISH market:prices ────────────▶│               │
    │                     │   { symbol, price, ts }              │               │
    │                     │                  │── fan-out ────────────────────────▶│
    │                     │                  │   to all subscribed clients       │
    │                     │                  │── Notification Svc evaluates alerts
    │                     │                  │                   │               │
REST client:
GET /api/v1/market/price/BTCUSDT ──▶ Gateway ──▶ Market Data Svc
                                                      │── GET from Redis cache (2s TTL)
                                                      │── if miss: fetch from Binance REST
                                                      ◀─ { price: 68420.50 }
```

---

## 9. Data Store Strategy

| Store | Technology | Usage | Per-service schema |
|---|---|---|---|
| **Primary DB** | PostgreSQL 16 | Users, sessions, orders, alerts, watchlist | Separate DB per service in prod |
| **Analytics DB** | TimescaleDB (PostgreSQL extension) | Time-series: P&L, prices, EI history | `alchemy_analytics` |
| **Cache** | Redis 7 | Prices (2s TTL), sessions, OTP, rate limits | Key namespacing: `svc:type:id` |
| **Message bus** | Redis Streams | Inter-service async events | `alchemy:events` stream |
| **Pub/Sub** | Redis Pub/Sub | Real-time broadcasts | `market:prices`, `alchemy:ws:broadcast` |
| **Vector store** | ChromaDB | LLM market memory (semantic search) | Intelligence Service only |
| **Secrets** | AES-256-GCM vault | Exchange API keys (in Trading Service DB) | Encrypted blob in PostgreSQL |

**Per-service database isolation (production):**
```
alchemy_auth     → Auth Service
alchemy_trading  → Trading Service
alchemy_risk     → Risk Service
alchemy_market   → Market Data Service (Redis primary, PG for history)
alchemy_intel    → Intelligence Service
alchemy_notify   → Notification Service
alchemy_admin    → Admin Service (read replicas of alchemy_auth + alchemy_trading)
```

---

## 10. Security at the Gateway

### Authentication Flow (Gateway-level)

Kong's JWT plugin verifies the RS256 token signature using the Auth Service's **public key** (stored in Kong's keyring). This means no round-trip to Auth Service for every request.

```
Request: Authorization: Bearer <JWT>
Kong:
  1. Decode JWT header → get kid (key ID)
  2. Fetch RS256 public key from keyring (cached in memory)
  3. Verify signature
  4. Check exp claim
  5. If valid: forward request + inject headers:
       X-User-ID: <sub claim>
       X-User-Plan: <subscription claim>
       X-User-Role: <role claim>
  6. If invalid: 401 immediately (never reaches service)
```

### Security Policies

| Policy | Mechanism | Applies to |
|---|---|---|
| **TLS** | Nginx terminates, Kong internal HTTPS | All |
| **JWT verification** | Kong JWT plugin (RS256) | All authenticated routes |
| **Rate limiting** | Kong Rate Limiting (Redis backend) | All routes |
| **IP restriction** | Kong IP Restriction plugin | `/api/v1/admin/**` |
| **CORS** | Kong CORS plugin | All |
| **mTLS** | Kong mTLS plugin | Inter-service (internal network) |
| **Secret scanning** | GitHub Actions + Gitleaks | CI/CD |
| **CSP headers** | Nginx + SecurityHeadersMiddleware | Web responses |
| **Input validation** | FastAPI/Pydantic (per service) | All service inputs |
| **SQL injection** | SQLAlchemy ORM (parameterised) | All DB queries |
| **Credential vault** | AES-256-GCM (Trading Service) | Exchange API keys |

---

## 11. Rate Limiting Strategy

Kong Rate Limiting Advanced replaces the current in-memory `InMemoryRateLimiter`.

| Route group | Free | Pro | Team | Enterprise |
|---|---|---|---|---|
| `/api/v1/auth/**` | 10/15min | 10/15min | 20/15min | 50/15min |
| `/api/v1/trading/orders` | 0 (blocked) | 100/min | 500/min | unlimited |
| `/api/v1/market/**` | 60/min | 300/min | 1000/min | unlimited |
| `/api/v1/ai/signal` | 5/day | 50/day | unlimited | unlimited |
| `/api/v1/admin/**` | blocked | blocked | 200/min | 500/min |
| `/ws` | 1 connection | 1 connection | 10 connections | unlimited |

Rate limit headers in response:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1713614265
Retry-After: 45  (only on 429)
```

---

## 12. Observability

```
Kong Access Logs (JSON)
    │
    ▼
Promtail ──▶ Loki ──▶ Grafana
    │                   │
    │              Kong dashboard:
    │              - Requests/sec per service
    │              - P50/P95/P99 latency
    │              - 4xx/5xx error rates
    │              - Rate limit hits per plan
    │
    ▼
Service Prometheus endpoints (/metrics)
    │
Prometheus ──▶ Grafana
                │
           Service dashboards:
           - Order execution latency
           - WS connection count
           - Redis hit/miss ratio
           - DB query time
           - LLM token usage
```

**Tracing:** OpenTelemetry spans injected at gateway, propagated via `traceparent` header to all services. Jaeger collector stores spans.

**Key SLOs:**

| Service | P95 Latency | Availability |
|---|---|---|
| Auth Service | < 200ms | 99.9% |
| Trading Service (order placement) | < 500ms | 99.95% |
| Market Data (cached) | < 50ms | 99.99% |
| Market Data (uncached) | < 300ms | 99.9% |
| Intelligence Service | < 3s | 99.5% |
| WebSocket Hub (message delivery) | < 100ms | 99.9% |

---

## 13. Docker Compose (Target)

```yaml
# docker-compose.prod.yml (target v1.0.0)
services:

  # ── Edge / TLS ───────────────────────────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/nginx-edge.conf:/etc/nginx/conf.d/default.conf:ro
      - ./ssl:/etc/letsencrypt:ro
    networks: [public]

  # ── API Gateway ──────────────────────────────────────────────────
  kong:
    image: kong:3.6-ubuntu
    environment:
      KONG_DATABASE: "off"
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: "0.0.0.0:8000"
      KONG_ADMIN_LISTEN: "0.0.0.0:8001"
      KONG_LOG_LEVEL: info
    volumes:
      - ./deploy/kong.yml:/etc/kong/kong.yml:ro
    expose: ["8000","8001"]
    networks: [public, internal]

  # ── Shared Infrastructure ────────────────────────────────────────
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: alchemy
    volumes: [pg_data:/var/lib/postgresql/data]
    networks: [internal]

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes: [redis_data:/data]
    networks: [internal]

  # ── Microservices ────────────────────────────────────────────────
  auth-svc:
    build: { context: ., dockerfile: services/auth/Dockerfile }
    expose: ["8001"]
    environment:
      DATABASE_URL: postgresql+asyncpg://alchemy:${DB_PASSWORD}@postgres/alchemy_auth
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
    networks: [internal]

  trading-svc:
    build: { context: ., dockerfile: services/trading/Dockerfile }
    expose: ["8002"]
    environment:
      DATABASE_URL: postgresql+asyncpg://alchemy:${DB_PASSWORD}@postgres/alchemy_trading
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      ALCHEMY_VAULT_KEY: ${ALCHEMY_VAULT_KEY}
    networks: [internal]

  market-svc:
    build: { context: ., dockerfile: services/market/Dockerfile }
    expose: ["8004"]
    environment:
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    networks: [internal]
    scale: 3  # Market data is stateless — run 3 replicas

  intelligence-svc:
    build: { context: ., dockerfile: services/intelligence/Dockerfile }
    expose: ["8005"]
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    networks: [internal]

  risk-svc:
    build: { context: ., dockerfile: services/risk/Dockerfile }
    expose: ["8003"]
    environment:
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      DATABASE_URL: postgresql+asyncpg://alchemy:${DB_PASSWORD}@postgres/alchemy_trading
    networks: [internal]

  notification-svc:
    build: { context: ., dockerfile: services/notification/Dockerfile }
    expose: ["8006"]
    environment:
      DATABASE_URL: postgresql+asyncpg://alchemy:${DB_PASSWORD}@postgres/alchemy_notify
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      FCM_SERVER_KEY: ${FCM_SERVER_KEY}
      APNS_KEY: ${APNS_KEY}
      SMTP_USER: ${SMTP_USER}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    networks: [internal]

  admin-svc:
    build: { context: ., dockerfile: services/admin/Dockerfile }
    expose: ["8007"]
    networks: [internal]

  ws-hub:
    build: { context: ., dockerfile: services/ws_hub/Dockerfile }
    expose: ["8008"]
    environment:
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    networks: [internal]
    scale: 2

  # ── Observability ────────────────────────────────────────────────
  prometheus:
    image: prom/prometheus:v2.51.0
    volumes:
      - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    networks: [internal]

  grafana:
    image: grafana/grafana:10.4.0
    volumes: [grafana_data:/var/lib/grafana]
    networks: [internal, public]

  loki:
    image: grafana/loki:2.9.0
    networks: [internal]

  jaeger:
    image: jaegertracing/all-in-one:1.55
    networks: [internal, public]
    expose: ["16686","4318"]

networks:
  public:
    driver: bridge
  internal:
    driver: bridge
    internal: true

volumes:
  pg_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

---

## 14. Kubernetes Helm Overview

For production at scale, a Helm chart wraps the microservices.

```
helm/alchemy/
├── Chart.yaml
├── values.yaml          ← override per environment
├── values.prod.yaml     ← production overrides
├── templates/
│   ├── gateway/
│   │   ├── kong-deployment.yaml
│   │   └── kong-configmap.yaml
│   ├── services/
│   │   ├── auth-deployment.yaml
│   │   ├── trading-deployment.yaml
│   │   ├── market-deployment.yaml   ← HPA: min 2, max 10 replicas
│   │   ├── intelligence-deployment.yaml
│   │   ├── risk-deployment.yaml
│   │   ├── notification-deployment.yaml
│   │   ├── admin-deployment.yaml
│   │   └── ws-hub-deployment.yaml   ← HPA: min 2, max 5 replicas
│   ├── infra/
│   │   ├── postgres-statefulset.yaml
│   │   ├── redis-statefulset.yaml
│   │   └── pvc.yaml
│   └── ingress.yaml                 ← Kong Ingress Controller
```

**HPA (Horizontal Pod Autoscaler) targets:**
- `market-svc`: CPU >60% → scale up (stateless, safe to scale)
- `ws-hub`: Connection count >500/pod → scale up
- `intelligence-svc`: CPU >70% → scale up (LLM calls are CPU-bound waiting)
- `auth-svc`: RPS >1000 → scale up

---

## 15. Migration Checklist

This checklist tracks the monolith-to-microservices migration. Each item can be done independently.

### Phase 0 — Prerequisites (v0.9.0)
- [x] Redis in docker-compose (already present)
- [ ] Wire Redis into `InMemoryRateLimiter` → `RedisRateLimiter`
- [ ] Replace `ConnectionManager` with Redis pub/sub
- [ ] Add `/api/v1/` prefix to all routes
- [ ] Add refresh token endpoint + `push_tokens` table
- [ ] Redis cache for market data routes

### Phase 1 — Gateway Layer (v0.9.5)
- [ ] Add Kong container to `docker-compose.prod.yml`
- [ ] Write `deploy/kong.yml` declarative config
- [ ] Route all traffic through Kong
- [ ] JWT verification moved to Kong (remove from individual services)
- [ ] Rate limiting moved to Kong (remove `RateLimitMiddleware` from FastAPI)

### Phase 2 — First Service Extraction (v0.10.0)
- [ ] Extract Market Data Service (stateless, lowest risk)
- [ ] Extract Notification Service (fire-and-forget, no synchronous dependencies)
- [ ] Both services run alongside monolith; Kong routes selectively

### Phase 3 — Core Services (v0.11.0)
- [ ] Extract Auth Service + PostgreSQL `alchemy_auth`
- [ ] Extract Risk Service
- [ ] WebSocket Hub as separate service with Redis pub/sub

### Phase 4 — Full Decomposition (v1.0.0)
- [ ] Extract Trading Service + PostgreSQL `alchemy_trading`
- [ ] Extract Intelligence Service
- [ ] Extract Admin Service
- [ ] Monolith retired
- [ ] Helm chart deployed to Kubernetes
- [ ] FCM / APNS push notifications live
- [ ] React Native mobile app v1.0 released
