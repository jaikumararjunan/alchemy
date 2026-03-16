# Alchemy — Autonomous AI Crypto Trading

**Alchemy** is a fully autonomous cryptocurrency trading system that uses Claude AI as its decision-making core. Rather than hard-coded rules, all trading decisions are delegated to Claude, which autonomously calls tools to gather data and execute trades on Delta Exchange.

---

## Table of Contents

1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Running the System](#running-the-system)
7. [Web Dashboard](#web-dashboard)
8. [Mobile App](#mobile-app)
9. [API Reference](#api-reference)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)
12. [Documentation Index](#documentation-index)

---

## Features

| Feature | Description |
|---------|-------------|
| **Autonomous AI Trading** | Claude AI calls tools in a loop — market data, news, technical indicators — and decides to BUY, SELL, HOLD, or CLOSE without human intervention |
| **Three Intelligence Layers** | Emotion (45%) + Geopolitical (25%) + Technical (30%) signals combined into a weighted score |
| **Risk-First Architecture** | Hard limits enforced independently of AI: daily loss cap, drawdown halt, per-trade risk cap, position count limit |
| **Paper Trading Mode** | Full dry-run simulation — all decisions logged, no real orders sent |
| **Real-Time Dashboard** | Single-file web UI with live price, equity curve, emotion meter, AI decision feed |
| **React Native Mobile App** | iOS + Android app with WebSocket-powered live updates and remote bot control |
| **Telegram Alerts** | Instant notifications for trade entries, stop triggers, daily summaries, and risk alerts |
| **Multi-Timeframe Analysis** | Signals aggregated across 1m, 5m, 15m, 1h, 4h, 1d timeframes with weighted confluence |
| **Trailing Stops** | Real-time WebSocket price monitor with automatic trailing stop management |
| **Docker Ready** | Single `docker compose up -d` to run the full stack |

---

## Architecture Overview

```
External Sources
  Delta Exchange API  │  RSS Feeds / NewsAPI  │  Anthropic Claude API
          │                     │                        │
          ▼                     ▼                        ▼
              ┌─────────────── CORE BACKEND ───────────────┐
              │                                            │
              │   News Fetcher → Emotion Engine (Claude)   │
              │   Delta Client (REST + WebSocket)          │
              │                                            │
              │   ┌─── AI ORCHESTRATOR (Claude tool_use) ─┐│
              │   │  get_market_data · analyze_news        ││
              │   │  get_technical_indicators              ││
              │   │  get_portfolio_state                   ││
              │   │  place_trade · close_position          ││
              │   └────────────────┬───────────────────────┘│
              │                   │                         │
              │   Risk Manager  Portfolio  Signal Aggregator │
              │                                            │
              │           FastAPI Server                   │
              │   REST endpoints │ WebSocket /ws │ Bot lifecycle│
              └──────────────────┬─────────────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
     Web Dashboard (dashboard/)         React Native App (mobile/)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the complete system design with data flow diagrams and component dependency maps.

---

## Prerequisites

### API Keys

| Service | Required | Purpose |
|---------|----------|---------|
| [Anthropic](https://console.anthropic.com) | Yes | Claude AI (decision engine + emotion analysis) |
| [Delta Exchange](https://www.delta.exchange) | Yes (live trading) | Trade execution API |
| [NewsAPI](https://newsapi.org) | No | Additional news sources |
| Telegram Bot (`@BotFather`) | No | Push notifications |

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 20.04 / macOS 12 | Ubuntu 22.04 LTS |
| Python | 3.10 | 3.11+ |
| RAM | 512 MB | 2 GB |
| Disk | 1 GB | 5 GB |
| Node.js | 18+ (mobile only) | 20 LTS |

---

## Quick Start

### 1. Clone and set up Python environment

```bash
git clone <repo-url> && cd alchemy
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env
```

Minimum for paper trading:

```env
ANTHROPIC_API_KEY=sk-ant-...
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
DRY_RUN=true
```

### 3. Start the server

```bash
python run_server.py --dry-run
# Server: http://localhost:8000
```

### 4. Start the bot

Click **▶ Start Bot** in the dashboard, or auto-start on launch:

```bash
python run_server.py --dry-run --start-bot
```

### 5. Open the dashboard

Navigate to `http://localhost:8000` — the dashboard connects via WebSocket and begins receiving live data on the first analysis cycle.

---

## Configuration

All configuration is managed via environment variables in `.env`. See `.env.example` for a complete template.

### Core Trading Parameters

```env
# ── Exchange ──────────────────────────────────────────────
DELTA_API_KEY=your_delta_api_key
DELTA_API_SECRET=your_delta_api_secret
DELTA_BASE_URL=https://api.india.delta.exchange

# ── AI ────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── News (optional) ───────────────────────────────────────
NEWS_API_KEY=your_newsapi_key

# ── Notifications (optional) ──────────────────────────────
TELEGRAM_BOT_TOKEN=123456:ABC-xyz
TELEGRAM_CHAT_ID=-100123456789

# ── Trading ───────────────────────────────────────────────
TRADING_SYMBOL=BTCUSD
POSITION_SIZE_USD=100          # Base position size; risk manager scales this
MAX_OPEN_POSITIONS=3
RISK_PER_TRADE_PCT=1.0         # Max % of balance per trade (hard cap)
BULLISH_THRESHOLD=0.6          # Combined score to trigger BUY  (0 to 1)
BEARISH_THRESHOLD=-0.6         # Combined score to trigger SELL (-1 to 0)
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=4.0
LEVERAGE=5

# ── Mode ──────────────────────────────────────────────────
DRY_RUN=true                   # true = paper trading, false = live
```

### Configuration Priority

`.env` file → system environment variables → dataclass defaults in `config.py`

---

## Running the System

### Server + Dashboard

```bash
# Paper trading, development (auto-reload on code changes)
python run_server.py --dry-run --reload

# Paper trading, auto-start bot at 15-minute intervals
python run_server.py --dry-run --start-bot --interval 15

# Live trading — ETHUSD, 30-minute cycles
python run_server.py --live --symbol ETHUSD --interval 30 --start-bot

# Custom port (e.g. behind a reverse proxy)
python run_server.py --dry-run --port 8080
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8000` | Port |
| `--dry-run` | — | Force paper trading |
| `--live` | — | Enable live trading |
| `--symbol` | `BTCUSD` | Trading pair |
| `--interval` | `30` | Analysis interval (minutes) |
| `--start-bot` | — | Auto-start bot 3s after launch |
| `--reload` | — | Dev hot-reload |

### Standalone Bot (no web server)

```bash
python main.py --dry-run --symbol BTCUSD --interval 30
python main.py --live --symbol ETHUSD --interval 60
```

### Docker

```bash
docker compose up -d          # Start
docker compose logs -f        # Live logs
docker compose down           # Stop
docker compose up -d --build  # Rebuild after code changes
```

---

## Web Dashboard

`dashboard/index.html` is a single-file vanilla JavaScript application — no build step. FastAPI serves it automatically at `http://localhost:8000`.

| Panel | Data | Update |
|-------|------|--------|
| Live Price Ticker | WebSocket | Real-time |
| Portfolio KPIs (equity, P&L, win rate, drawdown) | WebSocket | Per cycle |
| Emotion Intelligence (sentiment bars, AI reasoning) | WebSocket | Per cycle |
| Geopolitical Events | WebSocket | Per cycle |
| Equity Curve + Drawdown Chart | WebSocket | Per cycle |
| Technical Indicators (RSI, MACD, BB, EMA, trend) | WebSocket | Per cycle |
| AI Decision Feed | WebSocket | Per cycle |
| Trade History | WebSocket | Per cycle |
| News Feed | REST `/api/news` | 30s poll |

The dashboard auto-reconnects every 3 seconds on WebSocket disconnect and falls back to REST polling.

---

## Mobile App

A React Native (Expo 51) cross-platform app for iOS and Android.

### Setup

```bash
cd mobile
npm install

# Update server URL in mobile/src/services/api.js
# Use your machine's LAN IP for physical devices, not 'localhost'

npx expo start
# a → Android emulator
# i → iOS simulator
# Scan QR with Expo Go app for physical device
```

### Screens

| Screen | Features |
|--------|---------|
| **Dashboard** | Live price, portfolio KPIs, emotion meter, sentiment chart, bot controls |
| **Positions** | Open positions with P&L, trade history with SL/TP and AI reasoning |
| **Intelligence** | Emotion breakdown, geopolitical panel, AI decisions, news feed |
| **Settings** | Paper trade toggle, symbol picker, risk parameters, save to server |

### Production Build

```bash
npm install -g eas-cli
eas login && eas build:configure

eas build --platform android --profile preview   # APK
eas build --platform ios                         # IPA (requires Apple Developer)
```

---

## API Reference

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server + bot health |
| `GET` | `/api/status` | Bot state (cycle, mode, trades) |
| `GET` | `/api/config` | Current configuration |
| `POST` | `/api/config` | Update config (`symbol`, `dry_run`, thresholds) |
| `GET` | `/api/market/{symbol}` | Live ticker |
| `GET` | `/api/emotion` | Emotion scores + geo events + articles |
| `GET` | `/api/news?limit=N` | News articles with relevance scores |
| `GET` | `/api/positions` | Open positions |
| `GET` | `/api/portfolio` | Stats, equity curve, trade log |
| `GET` | `/api/decisions?limit=N` | AI decision history |
| `POST` | `/api/bot/control` | `{"action": "start"/"stop"/"cycle"}` |
| `POST` | `/api/trade` | Manual trade override |
| `WS` | `/ws` | Real-time WebSocket stream |

### Quick Reference

```bash
BASE=http://localhost:8000

# Health check
curl $BASE/health

# Start / stop / single cycle
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "start", "interval_minutes": 30}'
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "cycle"}'

# Switch to live trading
curl -X POST $BASE/api/config -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# Change symbol
curl -X POST $BASE/api/config -H "Content-Type: application/json" \
  -d '{"symbol": "ETHUSD"}'

# Portfolio, emotion, decisions
curl $BASE/api/portfolio | python -m json.tool
curl $BASE/api/emotion | python -m json.tool
curl "$BASE/api/decisions?limit=10" | python -m json.tool
```

### WebSocket Stream

Connect to `ws://localhost:8000/ws`. Each analysis cycle broadcasts:

```json
{
  "type": "cycle_complete",
  "portfolio": { "equity": 10250, "win_rate": 62.5 },
  "equity_curve": [{ "t": "...", "eq": 10250, "dd": 0.5 }],
  "cached_data": {
    "market":    { "mark_price": 95420, "bid": 95415, "ask": 95425 },
    "emotion":   { "sentiment_score": 0.42, "dominant_emotion": "optimism" },
    "geo":       { "total_impact": 0.18, "risk_level": "low" },
    "technicals":{ "rsi": 58.2, "macd": 124.5, "trend": "uptrend" },
    "bot_state": { "mode": "aggressive", "cycle": 14 }
  }
}
```

---

## Deployment

### systemd (Ubuntu VPS — recommended)

```bash
# /etc/systemd/system/alchemy.service
[Unit]
Description=Alchemy Autonomous AI Trading Bot
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/alchemy
Environment=PATH=/opt/alchemy/venv/bin:/usr/local/bin:/usr/bin
ExecStart=/opt/alchemy/venv/bin/python run_server.py --dry-run --start-bot --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable alchemy
sudo systemctl start alchemy
sudo journalctl -u alchemy -f    # Live logs
```

### Nginx + HTTPS (optional)

```nginx
server {
    server_name alchemy.yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the complete step-by-step deployment guide including Nginx HTTPS setup, Docker deployment, log management, and the full security checklist.

### Before Going Live — Safety Checklist

- [ ] Thoroughly tested in paper trading mode (`DRY_RUN=true`) for at least 10 cycles
- [ ] `POSITION_SIZE_USD` set to an amount you are comfortable losing entirely
- [ ] `RISK_PER_TRADE_PCT` ≤ 1% for initial live runs
- [ ] `MAX_OPEN_POSITIONS` = 1 for initial live runs
- [ ] Delta Exchange API key has **trade only** permissions (no withdrawal)
- [ ] Telegram notifications configured for immediate alerts
- [ ] `.env` not committed to git; permissions set: `chmod 600 .env`
- [ ] Server behind HTTPS if publicly accessible

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: fastapi` | venv not activated | `source venv/bin/activate && pip install -r requirements.txt` |
| `anthropic.AuthenticationError` | Bad API key | Check `ANTHROPIC_API_KEY` in `.env` |
| `Port 8000 already in use` | Port conflict | `lsof -i :8000` then `kill -9 <PID>`, or use `--port 8080` |
| WebSocket not connecting | Proxy headers missing | Add `Upgrade`/`Connection` headers in Nginx config |
| Bot running but no orders | Risk limits or low confidence | Check "Bot State" panel for `rejection_reason` |
| Delta `401 Unauthorized` | Clock drift or wrong key | `sudo timedatectl set-ntp true`; verify key in `.env` |
| Mobile "Network request failed" | Using `localhost` on device | Use LAN IP address in `mobile/src/services/api.js` |

For more detail see [docs/DEPLOYMENT.md § Troubleshooting](docs/DEPLOYMENT.md#10-troubleshooting).

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete system design: intelligence layers, AI orchestrator, risk engine, exchange integration, data flow, component map |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Step-by-step deployment: local, systemd, Nginx, Docker, monitoring, security |
| [.env.example](.env.example) | Annotated template for all environment variables |

---

## Tech Stack

**Backend:** Python 3.11, FastAPI, Anthropic SDK (`claude-opus-4-6` with `tool_use`), Delta Exchange REST + WebSocket, pandas, ta-lib, scikit-learn

**Frontend:** Vanilla JS + Chart.js 4.4 (no build step), React Native 0.74 + Expo 51, Zustand

**Infrastructure:** Docker, systemd, Nginx, Makefile, GitHub Actions
