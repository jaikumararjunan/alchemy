# Alchemy AI Trading Bot — User Guide

> **End-to-end guide for setup, configuration, operation, and monitoring of Alchemy.**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start](#2-quick-start)
3. [Installation](#3-installation)
4. [Configuration](#4-configuration)
5. [Running the Bot](#5-running-the-bot)
6. [Web Dashboard](#6-web-dashboard)
7. [REST API Reference](#7-rest-api-reference)
8. [Intelligence Layers](#8-intelligence-layers)
9. [Trading Strategy & Signals](#9-trading-strategy--signals)
10. [Risk Management](#10-risk-management)
11. [Contract Scanner](#11-contract-scanner)
12. [Machine Learning Features](#12-machine-learning-features)
13. [Derivatives Analytics](#13-derivatives-analytics)
14. [Backtesting](#14-backtesting)
15. [Mobile App](#15-mobile-app)
16. [Database & Storage](#16-database--storage)
17. [Alerts & Notifications](#17-alerts--notifications)
18. [Docker & Production Deployment](#18-docker--production-deployment)
19. [Monitoring & Observability](#19-monitoring--observability)
20. [Troubleshooting](#20-troubleshooting)
21. [Safety & Risk Rules](#21-safety--risk-rules)
22. [Glossary](#22-glossary)

---

## 1. Overview

Alchemy is an autonomous AI-powered cryptocurrency trading bot built on top of **Claude claude-opus-4-6**. It trades perpetual contracts on **Delta Exchange (India)** using a three-layer intelligence system:

| Layer | Weight | What It Does |
|-------|--------|--------------|
| Emotion Intelligence (Claude) | 45% | Reads news, detects fear/greed/panic/optimism |
| Geopolitical Analysis | 25% | Scores macro events (wars, sanctions, ETF news, etc.) |
| Technical Analysis | 30% | RSI, MACD, Bollinger Bands, ADX, VWAP |

**Key capabilities:**
- Fully autonomous trade execution (with hard risk guardrails)
- Multi-contract scanning across up to 15 symbols simultaneously
- Paper trading (dry-run) mode — safe to run without real money
- Real-time web dashboard and React Native mobile app
- Complete audit trail of every AI decision in SQLite
- Backtesting and parameter optimisation

---

## 2. Quick Start

### Minimum 5-minute setup (paper trading)

```bash
# 1. Clone and install
git clone <repo-url> alchemy && cd alchemy
make install-dev
make setup-env          # copies .env.example → .env

# 2. Add your Anthropic key (minimum required)
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# 3. Start the server (paper trading is ON by default)
python run_server.py --dry-run

# 4. Open dashboard
# http://localhost:8000
```

> Delta Exchange keys are **not required** for paper trading. The bot uses simulated market data when `DRY_RUN=true`.

---

## 3. Installation

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10, 3.11, or 3.12 |
| pip | latest |
| Docker + Compose | optional, for containerised runs |
| Node.js | 18+ (mobile app only) |

### Steps

```bash
# Production dependencies only
make install

# Development + test dependencies
make install-dev

# Copy environment template
make setup-env
# Then edit .env with your values
```

### Verify installation

```bash
python -c "from config import AppConfig; AppConfig()"
# Should print no errors
```

---

## 4. Configuration

All configuration is driven by environment variables loaded into dataclasses in `config.py`. **Never hardcode secrets** — always set them in `.env`.

### 4.1 Required Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key — required for all modes |
| `DELTA_API_KEY` | Delta Exchange API key — required for live trading only |
| `DELTA_API_SECRET` | Delta Exchange API secret — required for live trading only |

### 4.2 Safety

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | **Always start with `true`.** Paper trade mode; no real orders are placed |

### 4.3 Trading Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_SYMBOL` | `BTCUSD` | Primary trading symbol |
| `POSITION_SIZE_USD` | `100` | Default position size in USD |
| `MAX_OPEN_POSITIONS` | `3` | Hard cap on concurrent open positions |
| `RISK_PER_TRADE_PCT` | `1.0` | Capital risked per trade (%) |
| `BULLISH_THRESHOLD` | `0.6` | Composite score above this → BUY signal |
| `BEARISH_THRESHOLD` | `-0.6` | Composite score below this → SELL signal |
| `WATCH_LIST` | 10 symbols† | Comma-separated symbols to scan |
| `TOP_CONTRACTS_TO_TRADE` | `3` | Top N opportunities to act on |
| `SCAN_ALL_CONTRACTS` | `false` | Scan all watchlist symbols each cycle |

† Default watch-list: `BTCUSD,ETHUSD,SOLUSD,BNBUSD,XRPUSD,AVAXUSD,DOGEUSD,MATICUSD,LINKUSD,DOTUSD`

### 4.4 Risk Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `stop_loss_pct` | `2.0` | Default stop loss (%) |
| `take_profit_pct` | `4.5` | Default take profit (%) — keeps net R:R ≥ 1.5 after fees |
| `leverage` | `5` | Default leverage multiplier |
| `taker_fee_rate` | `0.0005` | 0.05% per side (Delta Exchange taker) |
| `maker_fee_rate` | `0.0002` | 0.02% per side |

### 4.5 Analysis Scheduling

| Variable | Default | Description |
|----------|---------|-------------|
| `analysis_interval_minutes` | `30` | Minutes between autonomous trading cycles |
| `fetch_interval_minutes` | `15` | How often to refresh news feeds |

### 4.6 Delta Exchange Connection

| Variable | Default |
|----------|---------|
| `DELTA_BASE_URL` | `https://api.india.delta.exchange` |
| WebSocket URL | `wss://socket.india.delta.exchange` (hardcoded) |

### 4.7 Alerts (Optional)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for trade alerts |
| `TELEGRAM_CHAT_ID` | Telegram chat/channel ID |

### 4.8 Monitoring (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_USER` | `admin` | Grafana dashboard user |
| `GRAFANA_PASSWORD` | `changeme_use_strong_password` | Change before production |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### 4.9 Validate configuration

After editing `.env`, always validate:

```bash
python -c "from config import AppConfig; AppConfig()"
```

A `ValueError` means a required key is missing.

---

## 5. Running the Bot

### 5.1 Modes at a glance

| Mode | Command | Description |
|------|---------|-------------|
| Paper trading (server) | `python run_server.py --dry-run` | Web dashboard + bot, no real orders |
| Paper trading (CLI) | `python main.py --dry-run` | Terminal-only, no web server |
| Single cycle | `python main.py --dry-run --symbol BTCUSD` | Run one cycle and exit |
| Live trading (server) | `python run_server.py --live --start-bot` | **Real orders — use with caution** |
| Docker (dev) | `make dev` | Hot-reload, all services |
| Docker (prod) | `make prod` | Production stack |

### 5.2 `run_server.py` — Server + Bot

Starts the FastAPI web server and optionally the autonomous bot.

```bash
python run_server.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Server bind address |
| `--port` | `8000` | Server port |
| `--start-bot` | off | Auto-start the autonomous bot on launch |
| `--dry-run` | env value | Force paper trading |
| `--live` | off | Force live trading (overrides DRY_RUN) |
| `--symbol` | env value | Override trading symbol |
| `--interval` | env value | Override cycle interval (minutes) |
| `--reload` | off | Auto-reload on code changes (dev only) |

**Examples:**

```bash
# Start server only, no bot (control via dashboard)
python run_server.py --dry-run

# Start server + auto-start bot in paper mode
python run_server.py --dry-run --start-bot

# Production: live trading, auto-start
python run_server.py --live --start-bot --port 8000
```

### 5.3 `main.py` — Standalone CLI Bot

Runs the bot without a web server. Useful for headless/cron setups.

```bash
python main.py [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Paper trading mode |
| `--live` | Enable live trading |
| `--symbol BTCUSD` | Override symbol |
| `--interval 30` | Override cycle interval (minutes) |

The CLI prints a rich terminal table each cycle showing emotion scores, geo events, technical indicators, generated signal, and risk check result.

### 5.4 Make shortcuts

```bash
make paper       # python run_server.py --dry-run --start-bot
make cycle       # single cycle via Docker
make dev         # Docker Compose, hot-reload, foreground
make dev-bg      # Docker Compose, background
make dev-bot     # Docker bot only (no web server)
```

---

## 6. Web Dashboard

Open **http://localhost:8000** after starting the server. The dashboard receives real-time updates via WebSocket.

### 6.1 Header Bar

| Element | Description |
|---------|-------------|
| Connection dot | Green = connected, Red = disconnected, animates on data |
| Mode badge | **DRY RUN** (amber) or **LIVE** (green) |
| Clock | Current UTC time |

### 6.2 Control Panel

| Control | Action |
|---------|--------|
| **Start Bot** | Begin autonomous trading cycles |
| **Stop** | Halt the bot immediately |
| **Run Cycle** | Trigger one analysis cycle manually |
| **Paper Trading ON** | Toggle dry-run mode on/off |
| Symbol dropdown | Switch trading symbol |
| Interval field | Set cycle interval in minutes |

> Changing the symbol or toggling dry-run takes effect at the next cycle.

### 6.3 KPI Cards

Four cards at the top of the dashboard:

| Card | Metrics |
|------|---------|
| **Portfolio Value** | Total equity ($) + all-time P&L (%) |
| **Daily P&L** | Today's profit/loss in $ and % |
| **Win Rate** | Winning trades ÷ total trades (%) |
| **Max Drawdown** | Peak-to-trough (%) + Profit Factor |

### 6.4 Market Card

Real-time ticker for the current symbol:

| Field | Description |
|-------|-------------|
| Price | Current mark price (large) |
| 24h Change | % change, colour-coded green/red |
| Volume 24h | USD turnover over last 24 hours |
| Bid / Ask | Best bid and ask from orderbook |
| Open Interest | Total open contracts (USD) |
| Spread % | (Ask − Bid) ÷ Mark × 100 |

### 6.5 Emotion Intelligence Card

Claude's real-time sentiment analysis:

| Field | Description |
|-------|-------------|
| Dominant Emotion | FEAR / GREED / PANIC / OPTIMISM / UNCERTAINTY / NEUTRAL |
| Sentiment Score | −1.0 (extreme fear) to +1.0 (extreme greed) |
| Needle gauge | Visual position on sentiment spectrum |
| Emotion bars | Fear, Greed, Panic, Optimism, Uncertainty (0–100%) |
| Geo Risk | LOW / MEDIUM / HIGH / CRITICAL |
| Trading Bias | STRONG BUY → STRONG SELL |
| Confidence | Model confidence in the analysis (%) |

### 6.6 Autonomous AI State Card

| Field | Description |
|-------|-------------|
| AI Mode | MONITORING / AGGRESSIVE / CONSERVATIVE / HALT |
| Cycles Run | Total analysis cycles completed |
| Total Trades | Trades executed this session |
| Open Positions | Currently open positions |
| Last Action | Most recent trade action + timestamp |
| Status Message | Rolling log of AI reasoning |

### 6.7 Equity Chart

Line chart of portfolio value over time with a drawdown overlay (red fill below zero).

### 6.8 Technical Indicators Grid

Nine indicators displayed as cards:

| Indicator | Signal Values |
|-----------|--------------|
| RSI (14) | Oversold / Neutral / Overbought |
| MACD | Bullish / Bearish + histogram value |
| Trend | Uptrend / Downtrend / Sideways |
| SMA 20 | Current value |
| BB Width % | Bollinger Band squeeze indicator |
| Volume Ratio | Current vs 20-period average |
| EMA 12 / EMA 26 | Values |
| ROC (10) | Rate of change % |

### 6.9 Geopolitical Events Panel

Lists up to 10 recent geo events with:
- Severity dot (red = critical, amber = high, blue = medium, green = low)
- Event category (WAR / REGULATION / MACRO / BANKING / ADOPTION)
- Region and impact score

### 6.10 AI Decision Feed

Scrollable list of each cycle's AI decision showing:
- Action (BUY / SELL / HOLD), price, stop-loss, take-profit
- Confidence % and Claude's reasoning text

### 6.11 Trade History Table

| Column | Description |
|--------|-------------|
| ID | Trade identifier |
| Symbol | Instrument |
| Side | BUY / SELL |
| Entry / Exit | Prices |
| Size | Position size in USD |
| P&L | Realised profit/loss |
| Status | OPEN / CLOSED |
| Conf % | AI confidence at entry |
| Time | Timestamp |

### 6.12 News Feed

Latest articles from RSS sources with relevance score badges. Sources: BBC, Reuters, NYT, Al Jazeera, WSJ, CryptoPanic.

---

## 7. REST API Reference

Base URL: `http://localhost:8000`

All responses are JSON. Error responses use standard HTTP status codes with `{"detail": "message"}`.

### 7.1 Health & Status

```
GET /health
```
```json
{
  "status": "ok",
  "bot_running": true,
  "ws_clients": 1,
  "dry_run": true,
  "symbol": "BTCUSD",
  "timestamp": "2026-03-13T10:00:00Z"
}
```

```
GET /api/status
```
```json
{
  "cycle_count": 12,
  "total_trades": 3,
  "current_mode": "monitoring",
  "last_action": "HOLD",
  "last_action_time": "2026-03-13T09:45:00Z",
  "status_message": "Waiting for high-confidence signal...",
  "dry_run": true,
  "symbol": "BTCUSD",
  "ws_clients": 1
}
```

### 7.2 Portfolio

```
GET /api/portfolio
```
```json
{
  "stats": {
    "total_equity": 1250.00,
    "total_pnl": 250.00,
    "total_pnl_pct": 25.0,
    "daily_pnl": 45.00,
    "daily_pnl_pct": 3.73,
    "win_rate": 0.67,
    "total_trades": 9,
    "winning_trades": 6,
    "max_drawdown_pct": 4.2,
    "profit_factor": 2.1
  },
  "equity_curve": [
    {"ts": "2026-03-12T00:00:00Z", "equity": 1000.00},
    ...
  ],
  "trades": [ ... ]
}
```

```
GET /api/positions
```
Returns array of open positions:
```json
[{
  "symbol": "BTCUSD",
  "side": "long",
  "size": 0.001,
  "entry_price": 84500.00,
  "liquidation_price": 70000.00,
  "unrealized_pnl": 55.00,
  "realized_pnl": 0.0,
  "leverage": 5
}]
```

### 7.3 Market Data

```
GET /api/market/{symbol}
```
```json
{
  "symbol": "BTCUSD",
  "mark_price": 85200.00,
  "last_price": 85180.00,
  "bid": 85195.00,
  "ask": 85205.00,
  "volume_24h": 982000000,
  "change_24h_pct": 2.14,
  "open_interest": 9800000000
}
```

### 7.4 Intelligence

```
GET /api/emotion
```
```json
{
  "emotion": {
    "sentiment_score": 0.42,
    "crypto_sentiment": 0.55,
    "dominant_emotion": "optimism",
    "confidence": 0.78,
    "geopolitical_risk": "low",
    "trading_bias": "buy",
    "key_events": ["Fed holds rates steady", "Bitcoin ETF inflows surge"],
    "reasoning": "Markets are cautiously optimistic following Fed's hold...",
    "emotions_breakdown": {
      "fear": 0.12, "greed": 0.45, "panic": 0.05,
      "optimism": 0.65, "uncertainty": 0.20
    }
  },
  "geopolitical": {
    "net_sentiment": 0.3,
    "total_impact": 0.28,
    "risk_level": "low",
    "bullish_pressure": 0.45,
    "bearish_pressure": 0.17,
    "event_count": 3
  },
  "articles_count": 42,
  "top_articles": [...]
}
```

```
GET /api/news?limit=20
```
Returns latest articles with `title`, `summary`, `source`, `url`, `relevance_score`, `published`.

```
GET /api/decisions?limit=20
```
Returns recent AI decisions from the database.

### 7.5 Bot Control

```
POST /api/bot/control
Content-Type: application/json

{"action": "start", "interval_minutes": 30}
```

| `action` value | Effect |
|----------------|--------|
| `"start"` | Start autonomous bot loop |
| `"stop"` | Stop the bot loop |
| `"cycle"` | Run exactly one cycle now |

### 7.6 Market Forecast

```
GET /api/forecast?symbol=BTCUSD
```
```json
{
  "symbol": "BTCUSD",
  "current_price": 85200.00,
  "adx": 28.4,
  "trend_direction": "bullish",
  "trend_strength": "moderate",
  "is_trending": true,
  "market_regime": "trending_up",
  "forecast_price_1": 85800.00,
  "forecast_price_3": 86400.00,
  "forecast_price_5": 87100.00,
  "forecast_bias": "bullish",
  "vwap": 84950.00,
  "vwap_position": "above",
  "support_levels": [84000, 82500],
  "resistance_levels": [86000, 88000],
  "breakeven_move_pct": 0.5,
  "round_trip_fee_pct": 0.5,
  "forecast_score": 0.68
}
```

### 7.7 Contract Scanner

```
GET /api/scanner/contracts
```
Returns current watch-list and top contract configuration.

```
GET /api/scanner/scan?symbols=BTCUSD,ETHUSD,SOLUSD
```
Runs a live scan and returns ranked opportunities.

```
GET /api/scanner/top?n=5
```
Returns top N opportunities from the most recent scan.

**Contract score fields:**
- `symbol`, `rank`, `composite_score` (0–1), `action` (buy/sell/hold), `confidence`
- `adx`, `market_regime`, `forecast_bias`
- `breakeven_move_pct`, `expected_move_pct`, `risk_reward_estimate`
- `suggested_size_pct` — recommended capital allocation %
- `reasoning` — explanation text

### 7.8 Machine Learning

```
GET /api/ml/analyze?symbol=BTCUSD
```
Returns ML-based price prediction, anomaly detection, and sentiment signal.

```
POST /api/ml/train
```
Triggers background model retraining. Returns `{"status": "training_started"}`.

```
GET /api/ml/status
```
Returns current ML model status and last training time.

```
POST /api/ml/sentiment
Content-Type: application/json

{"headlines": ["Bitcoin ETF sees record inflows", "Fed holds rates"]}
```
Returns per-headline sentiment scores plus aggregate.

### 7.9 Derivatives Analytics

```
GET /api/derivatives/funding?symbol=BTCUSD
```
```json
{
  "rate": 0.0001,
  "direction_signal": "bullish",
  "extreme_level": "normal"
}
```

```
GET /api/derivatives/basis?symbol=BTCUSD
```
```json
{
  "spot_price": 85050.00,
  "perp_price": 85200.00,
  "basis_pct": 0.18,
  "signal": "contango"
}
```

```
GET /api/derivatives/oi?symbol=BTCUSD
```
Open interest data with change % and signal.

```
GET /api/derivatives/signal
```
Aggregate derivatives signal combining funding, basis, OI, and liquidations.

### 7.10 Backtesting

```
POST /api/backtest/run
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "start_date": "2025-01-01",
  "end_date": "2026-01-01",
  "initial_capital": 10000,
  "position_size_usd": 500,
  "leverage": 5
}
```

```
POST /api/backtest/optimize
```
Runs parameter sweep over configurable ranges.

```
GET /api/backtest/defaults
```
Returns default backtest parameter values.

### 7.11 Manual Trading

```
POST /api/trade
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "side": "buy",
  "size_usd": 200,
  "stop_loss_pct": 2.0,
  "take_profit_pct": 4.5,
  "leverage": 5
}
```

> Manual trades still pass through the risk manager. They will be rejected if daily loss limits or max positions are exceeded.

### 7.12 Configuration

```
GET /api/config
```
```json
{
  "symbol": "BTCUSD",
  "dry_run": true,
  "interval_minutes": 30,
  "position_size_usd": 100,
  "leverage": 5
}
```

```
POST /api/config
Content-Type: application/json

{
  "symbol": "ETHUSD",
  "dry_run": false,
  "interval_minutes": 15,
  "position_size_usd": 250,
  "leverage": 3
}
```

All fields are optional — only provided fields are updated.

### 7.13 History

```
GET /api/history/trades?limit=100
GET /api/history/decisions?limit=50
GET /api/history/equity?days=30
```

### 7.14 WebSocket

```
ws://localhost:8000/ws
```

The server pushes a JSON update after every trading cycle. The payload structure:

```json
{
  "type": "cycle_complete",
  "cached_data": {
    "market": { ... },
    "emotion": { ... },
    "geo_impact": { ... },
    "technicals": { ... },
    "bot_state": { ... },
    "recent_decisions": [ ... ],
    "top_articles": [ ... ]
  },
  "portfolio": { ... },
  "equity_curve": [ ... ],
  "trade_log": [ ... ]
}
```

The dashboard uses this stream exclusively for live updates. New clients receive the last broadcast immediately on connection.

---

## 8. Intelligence Layers

### 8.1 Emotion Engine (Claude AI)

**File:** `src/intelligence/emotion_engine.py`
**Model:** `claude-opus-4-6` (do not downgrade — signal quality is model-sensitive)

The emotion engine feeds news articles into Claude and asks it to assess current market sentiment. It is the highest-weight intelligence layer (45%).

**Input:** Up to 50 recent news articles (title, summary, source, publish time)

**Output `EmotionScore`:**

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `sentiment_score` | float | −1.0 to +1.0 | Overall market mood |
| `dominant_emotion` | string | fear/greed/panic/optimism/pessimism/euphoria/uncertainty/neutral | Primary emotion |
| `emotions` | dict | 0.0–1.0 each | Fear, greed, panic, optimism, uncertainty intensities |
| `confidence` | float | 0.0–1.0 | Model confidence in analysis |
| `geopolitical_risk` | string | low/medium/high/critical | Macro risk level |
| `trading_bias` | string | strong_buy/buy/neutral/sell/strong_sell | Recommended bias |
| `key_events` | list[str] | 3–5 items | Most market-moving headlines |
| `crypto_specific_sentiment` | float | −1.0 to +1.0 | Crypto-specific impact only |
| `reasoning` | string | — | 2–3 sentence explanation |

### 8.2 Geopolitical Analyser

**File:** `src/intelligence/geo_analyzer.py`

Uses keyword matching and rule-based scoring. Faster than Claude for coarse filtering, runs before the emotion engine.

**Event categories:**

| Category | Example Triggers |
|----------|-----------------|
| `war` | armed conflict, military strike, troops |
| `sanctions` | trade war, economic sanctions |
| `regulation` | SEC, CFTC, crypto ban, crackdown |
| `macro` | interest rate, Fed, inflation, CPI |
| `banking_crisis` | bank failure, SVB, contagion |
| `adoption` | ETF approval, institutional buy, legal tender |

**Impact score examples:**

| Event | Score | Direction |
|-------|-------|-----------|
| Crypto ban / crackdown | −0.70 | Bearish |
| ETF approval | +0.80 | Bullish |
| Banking crisis | +0.70 | Bullish (BTC as safe haven) |
| Rate hike | −0.40 | Bearish |
| Monetary easing | +0.50 | Bullish |
| Capital controls | +0.50 | Bullish (crypto adoption) |

**Aggregate output:**

```json
{
  "net_sentiment": 0.3,
  "total_impact": 0.28,
  "risk_level": "low",
  "bullish_pressure": 0.45,
  "bearish_pressure": 0.17,
  "event_count": 3
}
```

### 8.3 Technical Analysis

**File:** `src/strategy/trading_strategy.py`

Computed from OHLCV candle data (100 periods, 1-hour resolution by default).

| Indicator | Parameters | Signal |
|-----------|-----------|--------|
| RSI | 14 | <30 oversold, >70 overbought |
| MACD | 12/26/9 | Histogram crossover |
| Bollinger Bands | 20, 2σ | Price vs. upper/lower band |
| SMA | 20-period | Price above/below |
| EMA | 12 and 26 | Crossover direction |
| ADX | 14 | >25 = trending, >40 = strong trend |
| ROC | 10-period | Momentum direction |
| ATR | 14 | Volatility baseline |
| VWAP | Session | Price position vs. VWAP |

---

## 9. Trading Strategy & Signals

### 9.1 Signal Generation

Each cycle, `TradingStrategy.generate_signal()` produces a weighted composite score:

| Source | Weight |
|--------|--------|
| Emotion (Claude) | 30% |
| Geopolitical | 15% |
| Technical indicators | 25% |
| Forecast (ADX/LR/VWAP) | 15% |
| Derivatives | 15% |

If the composite score exceeds `BULLISH_THRESHOLD` (0.6) → **BUY signal**
If it falls below `BEARISH_THRESHOLD` (−0.6) → **SELL signal**
Otherwise → **HOLD**

### 9.2 Signal Output

```python
TradeSignal:
  action: "buy" | "sell" | "close_long" | "close_short" | "hold"
  confidence: 0.0–1.0
  entry_price: float
  stop_loss: float
  take_profit: float
  position_size_multiplier: 0.0–1.0   # scales position size
  reasoning: str
  emotion_bias: str
  geo_risk_level: str
  signal_sources: list[str]
  breakeven_move_pct: float            # % to cover fees
  net_rr_after_fees: float             # R:R after round-trip fees
```

### 9.3 Signal Validation (`is_valid`)

A signal is considered actionable only when **all** of the following are true:
- `action` is buy, sell, close_long, or close_short (not hold)
- `confidence` ≥ 0.50
- `net_rr_after_fees` ≥ 1.5

Signals failing validation are logged but not forwarded to the risk manager.

### 9.4 Autonomous Agent Decision Framework

Each cycle the AI orchestrator follows this sequence:

```
1. SCAN          → scan_all_contracts       (rank all watched symbols)
2. FORECAST      → get_market_forecast      (ADX, regime, LR projection)
3. ANALYSE       → get_technical_indicators (RSI, MACD, BB, etc.)
4. SENTIMENT     → analyze_news_sentiment   (emotion + geo)
5. PORTFOLIO     → get_portfolio_state      (capital, positions, orders)
6. DECIDE        → synthesise signals       (2-of-3 layers must agree)
7. EXECUTE       → place_trade              (if conditions met)
8. DIVERSIFY     → up to 3 positions across different symbols
9. MONITOR       → update_stop_loss         (trailing stops)
```

**Agreement rule:** At least 2 of the 3 primary layers (emotion, geo, technicals) must point in the same direction before a trade is placed.

---

## 10. Risk Management

**File:** `src/risk/risk_manager.py`

The risk manager is the last gate before order placement. It **cannot be bypassed**.

### 10.1 Hard Limits

| Limit | Default | Trigger |
|-------|---------|---------|
| Daily loss limit | 5% | Halt all trading for the day |
| Drawdown warning | 8% | Reduce position sizes |
| Drawdown halt | 15% | Halt all trading until reset |
| Min R:R (net fees) | 1.5 | Reject trade |
| Min confidence | 0.50 | Reject trade |
| Max open positions | 3 | Reject new trades |

### 10.2 Fee Calculation

At default settings (5× leverage, 0.05% taker fee):
- **Round-trip fee** = 0.05% × 2 sides × 5× leverage = **0.50% of margin**
- `take_profit_pct` (4.5%) must clear the 0.50% fee to achieve net R:R ≥ 1.5

### 10.3 Risk Metrics Output

```python
RiskMetrics:
  account_balance: float
  available_balance: float
  used_margin: float
  open_positions: int
  daily_pnl: float
  daily_pnl_pct: float
  max_drawdown_pct: float
  risk_level: "green" | "yellow" | "red" | "halt"
  can_trade: bool
  rejection_reason: str | None
  round_trip_fee_pct: float
  estimated_fee_usd: float
```

### 10.4 Geopolitical Risk Gates

| Geo Risk Level | Effect |
|---------------|--------|
| `low` | Normal operation |
| `medium` | No change (monitor) |
| `high` | Reduce position size multiplier |
| `critical` | Halt new trades |

---

## 11. Contract Scanner

**File:** `src/scanner/contract_scanner.py`

The scanner ranks all watched symbols each cycle and identifies the best trading opportunities.

### 11.1 Default Watch-List

`BTCUSD`, `ETHUSD`, `SOLUSD`, `BNBUSD`, `XRPUSD`, `AVAXUSD`, `DOGEUSD`, `MATICUSD`, `LINKUSD`, `DOTUSD`, `ADAUSD`, `LTCUSD`, `ATOMUSD`, `NEARUSD`, `APTUSD`

### 11.2 Composite Scoring

| Component | Weight | Source |
|-----------|--------|--------|
| Forecast score | 50% | ADX, linear regression bias, VWAP position |
| Derivatives score | 30% | Funding rate, basis, open interest |
| Volatility bonus | 10% | ATR relative to price |
| Volume bonus | 10% | OI + 24h volume |

### 11.3 Scanner API

```
GET /api/scanner/top?n=5
```

Returns top N actionable contracts (confidence ≥ 0.45):

```json
{
  "top_opportunities": [
    {
      "symbol": "SOLUSD",
      "rank": 1,
      "composite_score": 0.72,
      "action": "buy",
      "confidence": 0.68,
      "current_price": 142.50,
      "change_24h_pct": 4.2,
      "adx": 32.1,
      "market_regime": "trending_up",
      "forecast_bias": "bullish",
      "breakeven_move_pct": 0.5,
      "expected_move_pct": 2.1,
      "risk_reward_estimate": 3.2,
      "suggested_size_pct": 15.0,
      "reasoning": "Strong ADX trend with bullish VWAP position..."
    }
  ],
  "total_scanned": 10,
  "total_actionable": 3
}
```

---

## 12. Machine Learning Features

**Directory:** `src/ml/`

Three ML models augment the core intelligence layers:

| Model | Purpose |
|-------|---------|
| Sentiment model | Classify headlines as bullish/bearish/neutral |
| Price prediction model | Short-term directional forecast |
| Anomaly detection model | Flag unusual market conditions |

### Usage via API

```bash
# Analyse specific headlines
curl -X POST http://localhost:8000/api/ml/sentiment \
  -H "Content-Type: application/json" \
  -d '{"headlines": ["Bitcoin hits new ATH", "SEC investigates exchange"]}'

# Full market ML analysis
curl http://localhost:8000/api/ml/analyze?symbol=BTCUSD

# Trigger retraining
curl -X POST http://localhost:8000/api/ml/train
```

---

## 13. Derivatives Analytics

**Directory:** `src/derivatives/`

| Endpoint | What It Analyses |
|----------|-----------------|
| `/api/derivatives/funding` | Funding rate direction — high positive = overcrowded longs |
| `/api/derivatives/basis` | Spot-perp spread — contango vs. backwardation |
| `/api/derivatives/oi` | Open interest changes — capital flow signal |
| `/api/derivatives/liquidations` | Liquidation heatmap — where stops are clustered |
| `/api/derivatives/options` | Options market sentiment (put/call ratio etc.) |
| `/api/derivatives/signal` | Aggregate signal combining all of the above |

**Interpreting funding rate:**
- Positive and high (>0.03%) → Market overleveraged long → potential short signal
- Negative → Market overleveraged short → potential long signal
- Near zero → Balanced → neutral

---

## 14. Backtesting

Run historical simulations before deploying a strategy live.

### Via API

```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD",
    "start_date": "2025-01-01",
    "end_date": "2026-01-01",
    "initial_capital": 10000,
    "position_size_usd": 500,
    "leverage": 5
  }'
```

### Parameter Optimisation

```bash
curl -X POST http://localhost:8000/api/backtest/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD",
    "parameter_ranges": {
      "bullish_threshold": [0.5, 0.6, 0.7],
      "stop_loss_pct": [1.5, 2.0, 2.5],
      "take_profit_pct": [3.0, 4.5, 6.0]
    }
  }'
```

Returns the parameter set with the highest Sharpe ratio.

---

## 15. Mobile App

**Directory:** `mobile/`
**Tech:** React Native 0.74.5 + Expo 51

### Setup

```bash
cd mobile
npm install
```

### Configure server URL

Edit `mobile/src/config.ts`:

```typescript
export const API_BASE_URL = "http://192.168.1.100:8000";  // your server IP
```

### Run

```bash
npx expo start          # dev server (scan QR with Expo Go)
npx expo run:android    # Android build
npx expo run:ios        # iOS build
```

### Features

The mobile app mirrors the web dashboard with:
- Real-time portfolio and P&L cards
- Live price and emotion gauge
- AI decision feed
- Trade history
- Bot start/stop controls
- Push notifications for trade executions (requires `expo-notifications` setup)

---

## 16. Database & Storage

**File:** `src/storage/`
**Engine:** SQLite 3 (WAL mode), auto-created at `alchemy.db`

### Tables

#### `trade_log`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `ts` | TEXT | ISO-8601 UTC timestamp |
| `symbol` | TEXT | Trading symbol |
| `side` | TEXT | `buy` or `sell` |
| `order_type` | TEXT | `market` or `limit` |
| `entry_price` | REAL | Entry price |
| `exit_price` | REAL | Exit price |
| `size_usd` | REAL | Position size in USD |
| `leverage` | INTEGER | Leverage used |
| `pnl_usd` | REAL | Realised P&L in USD |
| `pnl_pct` | REAL | Realised P&L % |
| `fee_usd` | REAL | Total fees paid |
| `stop_loss_pct` | REAL | Stop loss % at entry |
| `take_profit_pct` | REAL | Take profit % at entry |
| `exit_reason` | TEXT | `tp`, `sl`, `manual`, `signal` |
| `dry_run` | INTEGER | 0 = live, 1 = paper |
| `notes` | TEXT | Optional free text |

#### `decisions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `ts` | TEXT | ISO-8601 UTC timestamp |
| `symbol` | TEXT | Symbol analysed |
| `cycle` | INTEGER | Cycle number |
| `action` | TEXT | `BUY`, `SELL`, `HOLD`, `CLOSE` |
| `confidence` | REAL | Signal confidence 0–1 |
| `reasoning` | TEXT | Claude's explanation |
| `emotion_score` | REAL | Sentiment score at decision time |
| `geo_risk` | REAL | Geo impact score |
| `forecast_score` | REAL | Forecaster composite score |
| `market_regime` | TEXT | `trending_up`, `ranging`, etc. |
| `adx` | REAL | ADX value at decision time |
| `signal_score` | REAL | Final composite signal score |
| `dry_run` | INTEGER | 0 = live, 1 = paper |

#### `equity_snapshots`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `ts` | TEXT | ISO-8601 UTC timestamp |
| `balance` | REAL | Account balance |
| `unrealized_pnl` | REAL | Floating P&L |
| `total_equity` | REAL | Balance + unrealized |
| `open_positions` | INTEGER | Position count at snapshot |
| `cycle` | INTEGER | Cycle number |
| `dry_run` | INTEGER | 0 = live, 1 = paper |

### Query examples

```bash
# View last 10 decisions
sqlite3 alchemy.db "SELECT ts, symbol, action, confidence, reasoning FROM decisions ORDER BY id DESC LIMIT 10;"

# View trade stats
sqlite3 alchemy.db "SELECT side, COUNT(*), AVG(pnl_pct), SUM(pnl_usd) FROM trade_log WHERE dry_run=0 GROUP BY side;"

# View equity curve
sqlite3 alchemy.db "SELECT ts, total_equity FROM equity_snapshots ORDER BY id DESC LIMIT 20;"
```

---

## 17. Alerts & Notifications

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) → copy the token
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Add to `.env`:

```bash
TELEGRAM_BOT_TOKEN=7234567890:AAF...
TELEGRAM_CHAT_ID=123456789
```

Alchemy sends alerts for:
- Trade executed (entry price, symbol, side, confidence)
- Trade closed (exit reason, P&L)
- Risk limit triggered (daily loss, drawdown halt)
- Bot mode change (aggressive → conservative → halt)
- Error conditions

---

## 18. Docker & Production Deployment

### Development (hot-reload)

```bash
make dev          # foreground
make dev-bg       # background
make logs         # follow logs
make shell        # bash inside container
make stop         # stop all
```

### Production

```bash
# First-time setup
cp .env.example .env
# Edit .env with production values

# Start production stack
make prod

# Check health
make prod-status
make health

# Zero-downtime restart
make prod-restart
```

### Docker Compose files

| File | Use |
|------|-----|
| `docker-compose.yml` | Development (hot-reload, port 8000) |
| `docker-compose.prod.yml` | Production (with nginx, no reload) |

### Image details

- Multi-stage build (builder → runtime)
- Non-root user `alchemy` inside container
- Exposes port `8000`
- Data volume at `/app/alchemy.db`

### CI/CD (GitHub Actions)

**CI** runs on every push and PR:
1. Ruff lint check
2. pytest on Python 3.10, 3.11, 3.12
3. Docker build verification

**CD** runs on merge to `main`/`master`:
1. Build Docker image → push to registry
2. SSH to deploy host → pull + restart
3. Health check
4. Slack notification

Required GitHub secrets: `DELTA_API_KEY`, `DELTA_API_SECRET`, `ANTHROPIC_API_KEY`, `DOCKER_REGISTRY`, `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `SLACK_WEBHOOK_URL`

---

## 19. Monitoring & Observability

### Make targets

```bash
make health      # quick HTTP health check
make watch       # watch portfolio stats every 5 seconds
make ws          # connect to WebSocket stream (requires wscat)
make logs        # tail container logs
```

### Log format

Every module logs via `colorlog`:

```
2026-03-13 10:00:00 INFO  [ai_orchestrator] Cycle 42: BTCUSD — BUY signal, confidence=0.72
2026-03-13 10:00:01 INFO  [risk_manager]    Trade approved: R:R=2.1, fee_pct=0.50
2026-03-13 10:00:02 INFO  [delta_client]    Order placed: id=98765, side=buy, size=0.001
```

Log level is configurable via `LOG_LEVEL` env var.

### Grafana (optional)

Set `GRAFANA_USER` and `GRAFANA_PASSWORD` in `.env`, then access at **http://localhost:3000**.

---

## 20. Troubleshooting

### Bot not starting

```bash
# Check for config errors
python -c "from config import AppConfig; AppConfig()"

# Check server health
curl http://localhost:8000/health
```

### "Can't connect to Delta Exchange"

- Confirm `DELTA_BASE_URL` is `https://api.india.delta.exchange`
- Check API key/secret are correct in `.env`
- Verify keys have "Trade" and "Withdraw" permissions on Delta Exchange

### Bid/Ask showing stale values on dashboard

The dashboard only updates bid/ask when the new value is truthy. If switching from dry-run to live mode, trigger a manual cycle via **Run Cycle** to flush stale cache.

### Sentiment always 0.00 / Confidence 0%

- Confirm `ANTHROPIC_API_KEY` is set and valid
- Check news feeds are reachable: `curl https://feeds.bbci.co.uk/news/rss.xml`
- Check logs for `emotion_engine` errors: `make logs | grep emotion`

### "Daily loss limit exceeded"

The bot halted trading for the day. It will resume automatically at midnight UTC, or restart the server to reset the daily counter.

### Port 8000 already in use

```bash
# Find what's using it
lsof -i :8000

# Use a different port
python run_server.py --port 8080
```

### Database locked errors

SQLite WAL mode handles concurrent access. If you see lock errors:

```bash
# Stop all processes, then
sqlite3 alchemy.db "PRAGMA wal_checkpoint(FULL);"
```

---

## 21. Safety & Risk Rules

> These rules exist to protect real capital. They are **non-negotiable**.

1. **Always start with `DRY_RUN=true`** — run at least 48 hours in paper mode before going live.
2. **Do not modify `risk_manager.py` limits** without explicit testing — they are the last line of defence.
3. **Do not change the Claude model** in `AnthropicConfig` without benchmarking signal quality on historical data.
4. **Never commit `.env`** — only `.env.example` belongs in version control.
5. **Validate config changes** — run `python -c "from config import AppConfig; AppConfig()"` after every `.env` edit.
6. **Test storage migrations carefully** — changing the SQLite schema can corrupt historical data.
7. **Geopolitical CRITICAL → bot auto-halts** — review geo events before manually resuming.
8. **15% drawdown → bot auto-halts** — do not override this unless you understand the cause.
9. **Max 3 concurrent positions** — increasing this amplifies correlated risk.
10. **Min R:R 1.5 net of fees** — lowering this erodes edge over time.

---

## 22. Glossary

| Term | Definition |
|------|------------|
| **ADX** | Average Directional Index — measures trend strength (>25 = trending) |
| **Basis** | Difference between perpetual price and spot price |
| **Bollinger Bands** | Price volatility envelope (20-period SMA ± 2σ) |
| **Composite score** | Weighted sum of all intelligence layer scores (−1 to +1) |
| **Confidence** | AI's certainty in its decision (0.0–1.0). Minimum 0.50 to trade |
| **Contango** | Perp trading above spot (positive basis) |
| **Dry-run** | Paper trading mode — all logic runs but no real orders are placed |
| **EMA** | Exponential Moving Average |
| **Funding rate** | Periodic fee between long/short holders on perpetual contracts |
| **MACD** | Moving Average Convergence/Divergence momentum indicator |
| **Mark price** | Fair price calculated from spot index (used for liquidations) |
| **Max drawdown** | Largest peak-to-trough portfolio decline (%) |
| **OI** | Open Interest — total value of all open positions |
| **Profit factor** | Gross profit ÷ gross loss — values >1.5 indicate positive expectancy |
| **R:R** | Risk-Reward ratio — (TP − Entry) ÷ (Entry − SL) |
| **ROC** | Rate of Change — momentum indicator |
| **RSI** | Relative Strength Index — momentum oscillator (0–100) |
| **SMA** | Simple Moving Average |
| **VWAP** | Volume-Weighted Average Price — institutional reference price |
| **Win rate** | Winning trades ÷ total trades (%) |
