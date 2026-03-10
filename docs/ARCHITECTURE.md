# Alchemy — System Architecture

**Autonomous AI Crypto Trading on Delta Exchange**

---

## Table of Contents

1. [Overview](#1-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Intelligence Layer](#3-intelligence-layer)
4. [Autonomous AI Orchestrator](#4-autonomous-ai-orchestrator)
5. [Trading Engine](#5-trading-engine)
6. [Risk Management](#6-risk-management)
7. [Exchange Integration](#7-exchange-integration)
8. [Real-Time Infrastructure](#8-real-time-infrastructure)
9. [Web Dashboard](#9-web-dashboard)
10. [Mobile Application](#10-mobile-application)
11. [Data Flow](#11-data-flow)
12. [Configuration System](#12-configuration-system)
13. [Component Dependency Map](#13-component-dependency-map)

---

## 1. Overview

Alchemy is a fully autonomous cryptocurrency trading system that uses Claude AI as its decision-making core. Rather than hard-coded rules, the system delegates all trading decisions to Claude, which autonomously calls tools to gather data and execute trades.

### Three Intelligence Layers

| Layer | Weight | What It Analyzes |
|-------|--------|-----------------|
| **Emotion Intelligence** | 45% | Geopolitical news → market sentiment via Claude AI |
| **Geopolitical Analysis** | 25% | Event detection, impact scoring (war, regulation, macro) |
| **Technical Analysis** | 30% | RSI, MACD, Bollinger Bands, EMA, volume, trend |

### Key Design Principles

- **Autonomous by default** — Claude calls tools in a loop without human intervention
- **Risk-first** — hard limits enforced at the risk layer, not the AI layer
- **Real-time** — WebSocket price feeds, live sentiment updates, streaming dashboard
- **Multi-client** — same backend serves web dashboard and React Native mobile app
- **Paper-trade safe** — dry-run mode simulates all orders without execution

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SOURCES                            │
│  Delta Exchange API  │  RSS Feeds / NewsAPI  │  Anthropic Claude API │
└──────────┬───────────┴──────────┬────────────┴──────────┬───────────┘
           │                      │                        │
           ▼                      ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         CORE BACKEND (Python)                       │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Delta Client │  │ News Fetcher │  │   Emotion Engine          │  │
│  │ (REST + WS)  │  │ (RSS+API)    │  │   (Claude claude-opus-4-6)         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         │                 │                        │                │
│         ▼                 ▼                        ▼                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  AI ORCHESTRATOR (Claude tool_use)          │   │
│  │                                                             │   │
│  │  Tools: get_market_data · analyze_news_sentiment            │   │
│  │         get_technical_indicators · get_portfolio_state      │   │
│  │         place_trade · close_position · update_stop_loss     │   │
│  │         set_trading_mode · get_trade_history                │   │
│  └──────────────────────────────┬──────────────────────────────┘   │
│                                 │                                   │
│         ┌───────────────────────┼───────────────────┐              │
│         ▼                       ▼                   ▼              │
│  ┌─────────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │Risk Manager │  │ Portfolio Manager    │  │ Signal Aggregator│   │
│  │(sizing/halt)│  │ (P&L, equity curve)  │  │ (multi-timeframe)│   │
│  └─────────────┘  └──────────────────────┘  └─────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │               FastAPI Server  (server/api.py)                │  │
│  │    REST endpoints  │  WebSocket /ws  │  Bot lifecycle        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────────┘
                         │  WebSocket + REST
           ┌─────────────┴─────────────┐
           ▼                           ▼
  ┌─────────────────┐       ┌────────────────────┐
  │  Web Dashboard  │       │  React Native App  │
  │ (dashboard/)    │       │  (mobile/)         │
  └─────────────────┘       └────────────────────┘
```

---

## 3. Intelligence Layer

### 3.1 News Fetcher (`src/intelligence/news_fetcher.py`)

Aggregates news from multiple sources and scores each article for trading relevance.

**Sources:**
- 6 RSS feeds: BBC, Reuters, NY Times, Al Jazeera, WSJ, CryptoPanic
- NewsAPI (optional, requires API key)

**Relevance Scoring:**

| Signal | Score Boost |
|--------|-------------|
| Direct crypto mention (bitcoin, eth, regulation, sec) | +0.4 |
| High-impact keywords (war, nuclear, crisis, collapse) | +0.3 |
| Medium-impact keywords (inflation, rate hike, sanction) | +0.2 |
| Base keyword match | +0.1 |

Articles are sorted by relevance score and cached for 15 minutes to avoid redundant API calls. The `fetch_breaking()` method returns only articles with score ≥ 0.7 for urgent analysis.

---

### 3.2 Emotion Engine (`src/intelligence/emotion_engine.py`)

Sends news articles to Claude and receives a structured emotional market assessment.

**Output — `EmotionScore`:**

```
sentiment_score          float   -1.0 (extreme fear) → +1.0 (extreme greed)
confidence               float   0.0 → 1.0
dominant_emotion         str     fear | greed | optimism | pessimism | panic | euphoria | neutral
emotions                 dict    {fear: 0.6, greed: 0.2, panic: 0.1, ...}
geopolitical_risk        str     low | medium | high | critical
key_events               list    Top 3-5 market-moving event descriptions
trading_bias             str     strong_buy | buy | neutral | sell | strong_sell
reasoning                str     Claude's plain-text explanation
impact_horizon           str     immediate | short_term | medium_term
crypto_specific_sentiment float  -1.0 → 1.0 (crypto-only view)
```

**Claude prompt instructs it to consider:**
- Crypto's sensitivity to: regulation, macroeconomic fear/greed, geopolitical instability, banking crises, central bank policy, wars, sanctions
- Both short-term price reaction and medium-term trend direction
- Whether events are already priced in

---

### 3.3 Geopolitical Analyzer (`src/intelligence/geo_analyzer.py`)

Keyword-based event detection with pre-configured impact scores. Runs on top of news articles independently of Claude to provide an objective rules-based layer.

**Event Categories and Example Impacts:**

| Category | Event | Impact Score |
|----------|-------|-------------|
| Regulatory — Negative | ban, outlaw, prohibit | -0.70 |
| Regulatory — Negative | SEC lawsuit, fraud | -0.50 |
| Regulatory — Positive | ETF approved, spot bitcoin | +0.80 |
| Banking Crisis | bank run, banking crisis | +0.70 (flight to BTC) |
| Macro | hyperinflation | +0.60 |
| Macro | rate hike | -0.40 |
| Macro | rate cut, QE, dovish | +0.50 |
| War/Conflict | nuclear threat | -0.80 |
| War/Conflict | ceasefire, peace deal | +0.30 |
| Adoption | institutional buying | +0.60 |
| Adoption | bitcoin legal tender | +0.70 |

**Aggregate Output:**
```
total_impact       Weighted average of all detected events (-1.0 to 1.0)
bullish_pressure   Sum of positive impacts
bearish_pressure   Sum of negative impacts
net_sentiment      strongly_bullish | bullish | neutral | bearish | strongly_bearish
risk_level         critical | high | medium | low
dominant_events    Top 3 events with region and impact score
event_count        Total events detected across all articles
```

**Geopolitical Risk Dampening on Position Sizing:**

| Risk Level | Position Size Multiplier |
|------------|------------------------|
| low | 1.00× |
| medium | 0.80× |
| high | 0.50× |
| critical | No new positions |

---

## 4. Autonomous AI Orchestrator

**File:** `src/autonomous/ai_orchestrator.py`

This is the system's brain. Claude operates as a fully autonomous agent, calling tools iteratively to gather all the information it needs before making a trading decision.

### 4.1 Available Tools

| Tool | What It Does |
|------|-------------|
| `get_market_data` | Ticker + OHLCV candles (1m, 5m, 15m, 1h, 4h, 1d) + orderbook |
| `get_portfolio_state` | Balance, open positions, margin usage, P&L |
| `analyze_news_sentiment` | Fetch news → run emotion engine → return EmotionScore |
| `get_technical_indicators` | RSI, MACD, Bollinger Bands, EMA 12/26, SMA 20/50, volume ratio, trend |
| `place_trade` | Submit buy/sell order with SL/TP to Delta Exchange |
| `close_position` | Market-close an existing position |
| `update_stop_loss` | Adjust stop loss level on open position |
| `set_trading_mode` | Switch between `aggressive / conservative / monitoring / halt` |
| `get_trade_history` | Recent decisions + performance metrics |

### 4.2 System Prompt (Non-Negotiable Risk Rules)

```
You are ALCHEMY, a fully autonomous crypto trading AI.
You have complete authority to make trading decisions.

RISK RULES — NON-NEGOTIABLE:
1. Never risk more than 2% of account balance on a single trade
2. Always set stop losses before entering any position
3. Halt trading immediately if daily drawdown exceeds 5%
4. Reduce position size in high geopolitical risk environments
5. Never trade against strong momentum without confidence >= 0.75
6. Minimum risk:reward ratio of 1.5:1 required
```

### 4.3 Decision Cycle

```
┌─────────────────────────────────────────────────────┐
│  1. Claude receives autonomous prompt               │
│     (symbol, time, mode, dry-run flag, cycle #)     │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  2. Claude calls tools iteratively (agentic loop)   │
│                                                     │
│  get_market_data()         → price, candles         │
│  get_portfolio_state()     → balance, positions     │
│  analyze_news_sentiment()  → emotion score          │
│  get_technical_indicators()→ RSI, MACD, trend       │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  3. Claude synthesizes all data and decides         │
│                                                     │
│  Options: BUY · SELL · HOLD · CLOSE · MODE CHANGE  │
│  Must specify: SL, TP, confidence, reasoning        │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  4. Tool execution                                  │
│                                                     │
│  Dry run:  Decision logged, no order sent           │
│  Live:     place_trade() → Delta Exchange REST API  │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  5. Broadcast result                                │
│                                                     │
│  → Portfolio Manager (update equity curve)          │
│  → FastAPI WebSocket (push to dashboard + mobile)   │
│  → Decision log (last 50 decisions stored)          │
│  → Telegram Notifier (trade alerts)                 │
└─────────────────────────────────────────────────────┘
```

### 4.4 Trading Modes

| Mode | Behaviour |
|------|-----------|
| `monitoring` | Gather data, no new trades |
| `conservative` | Reduced position sizes, higher confidence threshold |
| `aggressive` | Full position sizes, standard thresholds |
| `halt` | No trading activity, close risky positions |

Claude can autonomously switch modes based on market conditions (e.g., switches to `halt` if daily drawdown approaches limit, switches to `aggressive` during high-conviction setups).

---

## 5. Trading Engine

### 5.1 Signal Aggregator (`src/autonomous/signal_aggregator.py`)

Generates independent signals across 6 timeframes and combines them via weighted average.

**Timeframe Weights:**

| Timeframe | Weight | Rationale |
|-----------|--------|-----------|
| 1m | 5% | Noise-heavy, low weight |
| 5m | 10% | Short-term confirmation |
| 15m | 15% | Entry timing |
| 1h | 25% | Primary trading timeframe |
| 4h | 25% | Trend direction |
| 1d | 20% | Market structure |

**Confluence Levels:**

| Agreement | Level | Action |
|-----------|-------|--------|
| ≥ 75% timeframes aligned | High | Full position size |
| ≥ 55% timeframes aligned | Medium | Reduced size |
| < 55% | Low | No entry |

---

### 5.2 Trading Strategy (`src/strategy/trading_strategy.py`)

Combines all intelligence signals into a single weighted score.

**Score Composition:**

```
combined_score =
    (emotion_signal   × 0.45) +
    (geo_signal       × 0.25) +
    (technical_signal × 0.30)
```

Where:
- `emotion_signal = (crypto_specific_sentiment × 0.6 + sentiment_score × 0.4) × confidence`
- `geo_signal = total_impact × risk_dampener[risk_level]`
- `technical_signal` = weighted combination of RSI, trend, momentum, BB position

**Decision Thresholds:**

| Score | Action |
|-------|--------|
| ≥ +0.60 | BUY |
| ≤ −0.60 | SELL |
| −0.60 to +0.60 | HOLD |
| Critical geo risk | No new positions |

**`TradeSignal` Output:**

```
action                   buy | sell | close_long | close_short | hold
confidence               0.0 → 1.0
entry_price              current market price
stop_loss                calculated from stop_loss_pct config
take_profit              calculated from take_profit_pct config
position_size_multiplier 0.0 → 1.0 (scales base position size)
reasoning                human-readable multi-part explanation
signal_sources           ["Claude AI (greed)", "Geo (2 events)", "Technical (uptrend)"]
risk_reward_ratio        property: (TP - entry) / (entry - SL)
is_valid                 property: confidence ≥ 0.5 AND R:R ≥ 1.5
```

---

## 6. Risk Management

**File:** `src/risk/risk_manager.py`

Hard safety limits enforced independently of AI decisions. Even if Claude decides to trade, the risk layer can block execution.

### 6.1 Hard Limits

| Rule | Threshold | Action |
|------|-----------|--------|
| Daily loss limit | −5.0% | HALT all trading |
| Drawdown warning | 8.0% | Reduce position size 50% |
| Drawdown halt | 15.0% | HALT all trading |
| Min risk:reward | 1.5:1 | Reject signal |
| Min confidence | 0.50 | Reject signal |
| Max open positions | 3 (configurable) | Block new entries |
| Max per-trade risk | 1% of balance | Cap position size |

### 6.2 Position Sizing Algorithm

```
base_size         = POSITION_SIZE_USD from config
quality_factor    = signal.position_size_multiplier (0.0–1.0)
max_loss_usd      = account_balance × RISK_PER_TRADE_PCT
risk_limited_size = max_loss_usd / stop_distance_pct
drawdown_factor   = 0.50 if drawdown ≥ 8% else 1.00
geo_factor        = risk_dampener[geo_risk_level]

final_size = min(base_size × quality_factor, risk_limited_size)
           × drawdown_factor
           × geo_factor
final_size = min(final_size, account_balance × 0.25)  # hard cap: 25% of balance
final_size = max(final_size, 10.0)                    # minimum: $10
```

### 6.3 Risk State Output

```python
RiskMetrics:
    account_balance       Current account balance
    used_margin           Margin committed to open positions
    available_balance     Balance available for new trades
    open_positions        Count of open positions
    daily_pnl / pct       Today's P&L and percentage
    max_drawdown_pct      Peak-to-trough drawdown
    risk_level            green | yellow | red | halt
    can_trade             Boolean
    rejection_reason      String explanation if blocked
```

---

## 7. Exchange Integration

**File:** `src/exchange/delta_client.py`

Handles all communication with Delta Exchange (India) — both REST API and WebSocket.

### 7.1 Authentication

All authenticated requests are signed using HMAC-SHA256:
```
signature = HMAC-SHA256(api_secret, timestamp + method + path + body)
Headers: api-key, timestamp, signature
```

### 7.2 REST Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/v2/tickers/{symbol}` | Current price, bid/ask, volume |
| GET | `/v2/history/candles` | OHLCV candles by resolution |
| GET | `/v2/l2orderbook/{symbol}` | Order book depth |
| GET | `/v2/wallet/balances` | Account balance (USDT) |
| GET | `/v2/positions/margined` | Open positions |
| POST | `/v2/orders` | Place order |
| DELETE | `/v2/orders` | Cancel order |
| POST | `/v2/products/orders/leverage` | Set leverage |

### 7.3 Order Types

| Scenario | Order Type | Flags |
|----------|-----------|-------|
| New long/short | `market` | standard |
| Closing position | `market` | `reduce_only: true` |
| Take profit | `limit` | `reduce_only: true` |
| Stop loss | `stop_market` | `reduce_only: true` |

---

## 8. Real-Time Infrastructure

### 8.1 WebSocket Price Monitor (`src/autonomous/ws_monitor.py`)

Maintains a persistent WebSocket connection to Delta Exchange for real-time price data.

**Connection:** `wss://socket.india.delta.exchange`

**Subscriptions:**
```json
{
  "type": "subscribe",
  "payload": {
    "channels": [
      {"name": "mark_price", "symbols": ["BTCUSD"]},
      {"name": "spot_price", "symbols": ["BTCUSD"]}
    ]
  }
}
```

**Trailing Stop Logic:**

For long positions:
1. Track `peak_price` — highest price seen since entry
2. On each new high: `new_stop = peak_price × (1 − trail_pct)`
3. Only raise stop, never lower
4. If `current_price ≤ current_stop` → trigger callback → close position

For short positions (symmetric, inverted).

**Reconnection:** Automatic reconnect after 5 seconds on any disconnect.

---

### 8.2 FastAPI Server (`server/api.py`)

Single process hosting REST API, WebSocket hub, and bot lifecycle management.

**REST Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Server + bot health check |
| GET | `/api/status` | Bot state (cycle, mode, trades) |
| GET | `/api/config` | Current configuration |
| POST | `/api/config` | Update config (symbol, dry-run, thresholds) |
| GET | `/api/market/{symbol}` | Live ticker data |
| GET | `/api/emotion` | Emotion scores + geo + articles |
| GET | `/api/news?limit=N` | News articles with relevance scores |
| GET | `/api/positions` | Open positions |
| GET | `/api/portfolio` | Stats + equity curve + trade log |
| GET | `/api/decisions?limit=N` | AI decision history |
| POST | `/api/bot/control` | `{"action": "start"/"stop"/"cycle"}` |
| POST | `/api/trade` | Manual trade override |
| WS | `/ws` | Real-time streaming |

**WebSocket Message Types:**

```json
// Broadcast on each cycle
{
  "type": "cycle_complete",
  "portfolio": { "equity": 10250, "win_rate": 62.5, ... },
  "equity_curve": [{"t": "...", "eq": 10250, "dd": 0.5}, ...],
  "trade_log": [...],
  "cached_data": {
    "market": { "mark_price": 95420, "bid": 95415, "ask": 95425, ... },
    "emotion": { "sentiment_score": 0.42, "dominant_emotion": "optimism", ... },
    "geo": { "total_impact": 0.18, "risk_level": "low", ... },
    "technicals": { "rsi": 58.2, "macd": 124.5, "trend": "uptrend", ... },
    "bot_state": { "mode": "aggressive", "cycle": 14, ... },
    "recent_decisions": [...],
    "top_articles": [...]
  }
}
```

**Bot Lifecycle:**
```
POST /api/bot/control {"action": "start"}
  → Creates asyncio background task
  → Loop: run_cycle() → sleep(interval) → repeat

POST /api/bot/control {"action": "stop"}
  → Cancels asyncio task

POST /api/bot/control {"action": "cycle"}
  → Runs single cycle immediately (no loop)
```

---

### 8.3 Telegram Notifier (`src/autonomous/notifier.py`)

Optional push notifications via Telegram Bot API.

**Notification Types:**

| Method | Trigger | Content |
|--------|---------|---------|
| `send_trade_signal()` | New order placed | Symbol, side, price, SL, TP, R:R, confidence, reasoning |
| `send_stop_triggered()` | Trailing stop hit | Symbol, entry, exit, P&L |
| `send_daily_summary()` | Scheduled (EOD) | Trades, win rate, P&L, profit factor, drawdown |
| `send_risk_alert()` | Risk limit warning | Alert type, details |
| `send_geo_alert()` | High-impact event | Event, region, crypto impact score |

**Setup:** Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Silently disabled if not configured.

---

## 9. Web Dashboard

**File:** `dashboard/index.html`

Single-file vanilla JavaScript application. No build step required — open directly or serve via FastAPI's static file mount.

### Panels

| Panel | Data Source | Update Method |
|-------|-------------|---------------|
| Live Price Ticker | WebSocket `market` | Real-time |
| KPI Cards (equity, P&L, win rate, drawdown) | WebSocket `portfolio` | Per cycle |
| Emotion Intelligence (sentiment bar, breakdown bars) | WebSocket `emotion` | Per cycle |
| Geopolitical Events List | WebSocket `geo` | Per cycle |
| AI State (mode, cycles, last action) | WebSocket `bot_state` | Per cycle |
| Equity Curve + Drawdown Chart | WebSocket `equity_curve` | Per cycle |
| Technical Indicators (9 indicators) | WebSocket `technicals` | Per cycle |
| Sentiment History Chart | Accumulated from WS | Per cycle |
| AI Decision Feed | WebSocket `recent_decisions` | Per cycle |
| Trade History Table | WebSocket `trade_log` | Per cycle |
| News Feed | REST `/api/news` | 30s polling |

**Charts:** Chart.js 4.4 (CDN). Equity curve uses dual Y-axis (equity left, drawdown % right).

**Fallback:** If WebSocket is disconnected, falls back to 30-second REST polling of all endpoints.

---

## 10. Mobile Application

**Directory:** `mobile/`

React Native (Expo 51) cross-platform app targeting iOS and Android.

### Tech Stack

| Concern | Library |
|---------|---------|
| Framework | React Native 0.74 + Expo 51 |
| Navigation | React Navigation 6 (bottom tabs) |
| State | Zustand 4 |
| Charts | react-native-chart-kit |
| Icons | @expo/vector-icons (Ionicons) |
| Haptics | expo-haptics |
| Push Notifications | expo-notifications |

### Screens

**Dashboard (`DashboardScreen.js`)**
- Connection status + bot mode badge
- Live price ticker with 24h change badge, bid/ask
- Portfolio KPI cards (equity, daily P&L, win rate, drawdown)
- Emotion meter with animated sentiment bar
- Sentiment history line chart
- Bot controls (Start / Stop / Run Cycle)

**Positions (`PositionsScreen.js`)**
- Portfolio summary grid (total P&L, balance, unrealized, avg win/loss)
- Open positions with entry, size, leverage, liquidation price, unrealized P&L
- Trade history with side badges, status badges, SL/TP, confidence, reasoning

**Intelligence (`IntelligenceScreen.js`)**
- Emotion breakdown bars (fear, greed, panic, optimism, uncertainty)
- Sentiment score + confidence + crypto-specific sentiment
- Claude AI reasoning block
- Key events list
- Geopolitical impact panel (bullish/bearish pressure, dominant events)
- AI decision feed
- Live news feed with relevance scores

**Settings (`SettingsScreen.js`)**
- Paper trading toggle (dry-run switch)
- Symbol picker (BTCUSD, ETHUSD, SOLUSD, BNBUSD, ADAUSD, DOTUSD)
- Risk parameters (position size, risk %, SL %, TP %, leverage, max positions)
- Analysis interval
- Confidence thresholds
- Save to server via `POST /api/config`

### State Management (Zustand)

The global store (`store/useStore.js`) holds all application state and exposes a `processWSData()` action that parses incoming WebSocket messages and updates all relevant slices atomically:

```
market → setMarket()
emotion → setEmotion() + addSentimentPoint()
geo → setGeo()
technicals → setTechnicals()
bot_state → setBotState()
portfolio → setPortfolio()
equity_curve → setEquityCurve()
trade_log → setTrades()
recent_decisions → setDecisions()
top_articles → setNews()
```

---

## 11. Data Flow

### Full Analysis Cycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ANALYSIS CYCLE                               │
│                                                                     │
│  1. News Fetcher polls RSS + NewsAPI (15-min cache)                 │
│     → Articles scored by relevance (0.0 – 1.0)                     │
│                                                                     │
│  2. Geo Analyzer scans articles for geopolitical keywords           │
│     → GeopoliticalEvent objects with impact scores                  │
│     → Aggregate: total_impact, risk_level, dominant_events          │
│                                                                     │
│  3. Claude AI Orchestrator starts agentic loop                      │
│     Tool calls (in Claude's discretion):                            │
│     a. get_market_data     → ticker + candles (6 timeframes)        │
│     b. analyze_news        → EmotionScore from Claude               │
│     c. get_technicals      → RSI, MACD, BB, EMA, trend              │
│     d. get_portfolio_state → balance, positions, daily P&L          │
│                                                                     │
│  4. Claude synthesises all data                                     │
│     → Weighted score = emotion(45%) + geo(25%) + technical(30%)     │
│     → Decision: BUY / SELL / HOLD / CLOSE / MODE CHANGE            │
│     → Parameters: SL, TP, confidence, position_size, reasoning      │
│                                                                     │
│  5. Risk Manager validates decision                                 │
│     → Check: daily loss, drawdown, position count, R:R, confidence  │
│     → Calculate: final position size in USD                         │
│     → Return: can_trade boolean + rejection_reason                  │
│                                                                     │
│  6. Execution                                                       │
│     Dry run  → Decision logged, no API call                         │
│     Live     → Delta Exchange REST API: POST /v2/orders             │
│                                                                     │
│  7. Portfolio Manager updates                                       │
│     → Equity curve point added                                      │
│     → Trade log updated                                             │
│     → Performance stats recalculated                                │
│                                                                     │
│  8. Broadcast                                                       │
│     → All WebSocket clients receive full state JSON                 │
│     → Telegram notification if trade placed or stop triggered       │
│     → Cycle counter incremented                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Real-Time Price Monitoring (between cycles)

```
Delta Exchange WebSocket
    → mark_price / spot_price events
    → DeltaWSMonitor._on_message()
    → Update _prices[symbol]
    → Check TrailingStop for symbol
        → If long: raise stop if new peak
        → If triggered: on_stop_trigger() callback
            → close_position() via Delta API
            → Telegram: send_stop_triggered()
            → Remove trailing stop from registry
```

---

## 12. Configuration System

**File:** `config.py`

Dataclass-based configuration with environment variable loading.

```python
@dataclass
class TradingConfig:
    symbol: str                       # "BTCUSD"
    position_size_usd: float          # 100.0
    max_open_positions: int           # 3
    risk_per_trade_pct: float         # 1.0
    stop_loss_pct: float              # 2.0
    take_profit_pct: float            # 4.0
    leverage: int                     # 5
    bullish_threshold: float          # 0.60
    bearish_threshold: float          # -0.60
    analysis_interval_minutes: int    # 30
    dry_run: bool                     # True
```

**Priority order:** `.env` file → system environment variables → dataclass defaults.

**Validation:** `config.validate()` raises `ValueError` if Anthropic API key or Delta API credentials are missing when `dry_run=False`.

---

## 13. Component Dependency Map

```
run_server.py / main.py
    └── config.py                       (global config singleton)
    └── server/api.py                   (FastAPI application)
            ├── src/exchange/delta_client.py
            ├── src/intelligence/
            │       ├── news_fetcher.py
            │       ├── emotion_engine.py   → anthropic SDK
            │       └── geo_analyzer.py
            ├── src/strategy/trading_strategy.py
            │       └── (uses EmotionScore + GeoAggregate + technicals)
            ├── src/risk/risk_manager.py
            ├── src/autonomous/
            │       ├── ai_orchestrator.py  → anthropic SDK (tool_use)
            │       │       ├── delta_client.py  (tool implementations)
            │       │       ├── emotion_engine.py
            │       │       ├── news_fetcher.py
            │       │       └── portfolio_manager.py
            │       ├── portfolio_manager.py
            │       ├── signal_aggregator.py
            │       ├── ws_monitor.py       → websocket-client
            │       └── notifier.py         → requests → Telegram API
            └── src/utils/logger.py

dashboard/index.html                    (standalone, fetches from FastAPI)
mobile/                                 (React Native, fetches from FastAPI)
    └── src/services/api.js             (REST + WebSocket client)
    └── src/store/useStore.js           (Zustand global state)
    └── src/screens/                    (4 screens)
```
