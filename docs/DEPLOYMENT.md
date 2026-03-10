# Alchemy — Deployment Guide

**Autonomous AI Crypto Trading System**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start](#2-quick-start)
3. [Configuration Reference](#3-configuration-reference)
4. [Running the Server](#4-running-the-server)
5. [Running the Mobile App](#5-running-the-mobile-app)
6. [Telegram Notifications Setup](#6-telegram-notifications-setup)
7. [Production Deployment](#7-production-deployment)
8. [Docker Deployment](#8-docker-deployment)
9. [Monitoring & Logs](#9-monitoring--logs)
10. [Troubleshooting](#10-troubleshooting)
11. [Security Checklist](#11-security-checklist)

---

## 1. Prerequisites

### API Keys Required

| Service | Purpose | Get it at |
|---------|---------|-----------|
| **Anthropic** | Claude AI (required) | console.anthropic.com |
| **Delta Exchange** | Trade execution (required for live) | delta.exchange → API Keys |
| **NewsAPI** | Additional news sources (optional) | newsapi.org |
| **Telegram Bot** | Push notifications (optional) | @BotFather on Telegram |

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 20.04 / macOS 12 | Ubuntu 22.04 LTS |
| Python | 3.10 | 3.11+ |
| RAM | 512 MB | 2 GB |
| CPU | 1 core | 2 cores |
| Disk | 1 GB | 5 GB |
| Network | Stable internet | Low-latency VPS |

### Node.js (mobile app only)

- Node.js 18+ (for React Native / Expo)
- Install Expo CLI: `npm install -g @expo/cli`

---

## 2. Quick Start

### Step 1 — Clone and set up Python environment

```bash
# Clone the repository
git clone <repo-url> && cd alchemy

# Create virtual environment
python -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2 — Configure environment

```bash
cp .env.example .env
nano .env                         # or your preferred editor
```

Minimum required fields for **paper trading**:
```env
ANTHROPIC_API_KEY=sk-ant-...
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
DRY_RUN=true
```

### Step 3 — Start the server

```bash
# Paper trading mode (safe, no real orders)
python run_server.py --dry-run

# Server starts at http://localhost:8000
# Open dashboard: http://localhost:8000
```

### Step 4 — Start the bot

In the web dashboard, click **▶ Start Bot** — or pass `--start-bot` on launch:

```bash
python run_server.py --dry-run --start-bot
```

### Step 5 — View the dashboard

Open `http://localhost:8000` in any browser. The dashboard auto-connects via WebSocket and begins receiving live data when the bot runs its first cycle.

---

## 3. Configuration Reference

### Complete `.env` File

```env
# ─── Delta Exchange API ─────────────────────────────────
DELTA_API_KEY=your_delta_api_key
DELTA_API_SECRET=your_delta_api_secret
DELTA_BASE_URL=https://api.india.delta.exchange

# ─── Anthropic Claude API ───────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ─── News Sources ───────────────────────────────────────
NEWS_API_KEY=your_newsapi_key          # Optional

# ─── Telegram Notifications ─────────────────────────────
TELEGRAM_BOT_TOKEN=123456:ABC-xyz      # Optional
TELEGRAM_CHAT_ID=-100123456789         # Optional

# ─── Trading Parameters ─────────────────────────────────
TRADING_SYMBOL=BTCUSD                  # Symbol to trade
POSITION_SIZE_USD=100                  # Base position size in USD
MAX_OPEN_POSITIONS=3                   # Max simultaneous positions
RISK_PER_TRADE_PCT=1.0                 # Max % of balance per trade

# ─── Sentiment Thresholds ───────────────────────────────
BULLISH_THRESHOLD=0.6                  # Score to trigger buy (0 to 1)
BEARISH_THRESHOLD=-0.6                 # Score to trigger sell (-1 to 0)

# ─── Mode ───────────────────────────────────────────────
DRY_RUN=true                           # true = paper trading, false = live
```

### Key Parameters Explained

**`POSITION_SIZE_USD`**
The base dollar amount per trade before any scaling. The risk manager may reduce this based on confidence, geopolitical risk, and drawdown. Set conservatively — the AI will scale up with high-confidence setups.

**`RISK_PER_TRADE_PCT`**
Hard cap: never lose more than this percentage of account balance on a single trade. At 1.0%, a $10,000 account will never risk more than $100 on any position regardless of position size setting.

**`BULLISH_THRESHOLD` / `BEARISH_THRESHOLD`**
The combined weighted score must exceed these thresholds to trigger a trade. Higher absolute values (e.g., 0.75 / -0.75) = fewer, higher-conviction trades. Lower values = more frequent trading.

**`MAX_OPEN_POSITIONS`**
The bot will not open new positions once this count is reached. Existing positions can still be closed or have stops adjusted.

---

## 4. Running the Server

### CLI Options

```bash
python run_server.py [options]

Options:
  --host HOST         Bind host (default: 0.0.0.0)
  --port PORT         Port to listen on (default: 8000)
  --start-bot         Auto-start autonomous bot 3 seconds after launch
  --live              Enable live trading (disables dry-run)
  --dry-run           Force paper trading (overrides .env)
  --symbol SYMBOL     Override trading symbol (e.g. ETHUSD)
  --interval MINUTES  Override analysis interval in minutes
  --reload            Enable auto-reload for development
```

### Common Launch Patterns

```bash
# Development — paper trading, auto-reload on code changes
python run_server.py --dry-run --reload

# Paper trading with auto-start
python run_server.py --dry-run --start-bot --interval 15

# Live trading — ETH, 30-minute cycles, bot auto-starts
python run_server.py --live --symbol ETHUSD --interval 30 --start-bot

# Custom port (useful behind a reverse proxy)
python run_server.py --dry-run --port 8080
```

### Standalone Bot (no web server)

If you only want the trading bot without the web dashboard:

```bash
python main.py --dry-run --symbol BTCUSD --interval 30
python main.py --live                              # Live trading
python main.py --live --interval 60 --symbol ETHUSD
```

### Verifying the Server is Running

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", "bot_running": false, "mode": "monitoring", ...}

curl http://localhost:8000/api/status
# Bot state details

curl http://localhost:8000/api/emotion
# Latest emotion analysis
```

---

## 5. Running the Mobile App

### Install Dependencies

```bash
cd mobile
npm install
```

### Connect to Your Server

Edit `mobile/src/services/api.js` and update the server URLs:

```javascript
// For device on same WiFi as server
const BASE_URL = __DEV__ ? 'http://192.168.1.100:8000' : 'http://your-vps-ip:8000';
const WS_URL  = __DEV__ ? 'ws://192.168.1.100:8000/ws' : 'ws://your-vps-ip:8000/ws';
```

> **Note:** Use your server's local IP address (not `localhost`) when running on a physical device. Run `ifconfig` or `ip addr` to find it.

### Start the Expo Development Server

```bash
cd mobile
npx expo start
```

This opens Expo Dev Tools in your browser with options to:
- Press `a` — open on Android emulator
- Press `i` — open on iOS simulator
- Scan QR code with **Expo Go** app on your physical device

### Build for Production

```bash
# Install EAS CLI
npm install -g eas-cli

# Login and configure
eas login
eas build:configure

# Build for Android (APK)
eas build --platform android --profile preview

# Build for iOS (requires Apple Developer account)
eas build --platform ios
```

---

## 6. Telegram Notifications Setup

### Step 1 — Create a Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token (format: `123456789:ABCdef...`)

### Step 2 — Get Your Chat ID

1. Send any message to your new bot
2. Open this URL in a browser (replace `TOKEN` with your bot token):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
3. Find `"chat": {"id": -100123456789}` in the response — that is your Chat ID

For **group notifications**: Add the bot to a group and use the group's negative ID.

### Step 3 — Add to `.env`

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=-100123456789
```

### Step 4 — Test

Restart the server. The first time the bot executes a trade or detects a significant geopolitical event, you will receive a Telegram message.

### Alert Types You Will Receive

```
📊 BUY BTCUSD
💰 Price: $95,420.00
🛑 Stop Loss: $93,512.00
🎯 Take Profit: $99,237.00
📈 Risk:Reward: 2.00:1
🧠 Confidence: 78%

Reasoning: Strong bullish emotion (greed dominates), positive
geopolitical shift after rate cut announcement...
```

---

## 7. Production Deployment

### Recommended: Ubuntu VPS + systemd

#### Step 1 — Set Up Server

```bash
# Update and install Python
sudo apt update && sudo apt upgrade -y
sudo apt install python3.11 python3.11-venv python3.11-dev git -y

# Clone repo
git clone <repo-url> /opt/alchemy
cd /opt/alchemy

# Set up venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env                         # Add your API keys
```

#### Step 2 — Create systemd Service

```bash
sudo nano /etc/systemd/system/alchemy.service
```

```ini
[Unit]
Description=Alchemy Autonomous AI Trading Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/alchemy
Environment=PATH=/opt/alchemy/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=/opt/alchemy/venv/bin/python run_server.py --dry-run --start-bot --port 8000
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable alchemy
sudo systemctl start alchemy

# Check status
sudo systemctl status alchemy
sudo journalctl -u alchemy -f      # Live logs
```

#### Step 3 — Nginx Reverse Proxy (optional, for HTTPS)

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo nano /etc/nginx/sites-available/alchemy
```

```nginx
server {
    server_name alchemy.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;    # Required for WebSocket
    }

    listen 80;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/alchemy /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Add HTTPS
sudo certbot --nginx -d alchemy.yourdomain.com
```

> **WebSocket note:** The `Upgrade` and `Connection` headers are required for WebSocket to work through Nginx. The `proxy_read_timeout 86400` prevents Nginx from killing idle WebSocket connections.

#### Step 4 — Update Mobile App for Production

In `mobile/src/services/api.js`:
```javascript
const BASE_URL = __DEV__ ? 'http://localhost:8000' : 'https://alchemy.yourdomain.com';
const WS_URL  = __DEV__ ? 'ws://localhost:8000/ws' : 'wss://alchemy.yourdomain.com/ws';
```

---

## 8. Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Expose port
EXPOSE 8000

# Start server
CMD ["python", "run_server.py", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  alchemy:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - DRY_RUN=${DRY_RUN:-true}
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### Running with Docker

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Restart after code changes
docker compose up -d --build
```

---

## 9. Monitoring & Logs

### Log Levels

Alchemy uses Python's `logging` module with colour formatting via `colorlog`.

| Logger | What it covers |
|--------|---------------|
| `alchemy.orchestrator` | AI cycle execution, tool calls, decisions |
| `alchemy.exchange` | API requests, order placement |
| `alchemy.intelligence` | News fetching, emotion analysis |
| `alchemy.risk` | Risk checks, position sizing |
| `alchemy.server` | HTTP requests, WebSocket events |

### Viewing Logs

```bash
# Direct (development)
python run_server.py --dry-run 2>&1 | tee alchemy.log

# systemd (production)
sudo journalctl -u alchemy -f
sudo journalctl -u alchemy --since "1 hour ago"
sudo journalctl -u alchemy --since today

# Filter by component
sudo journalctl -u alchemy -f | grep orchestrator
sudo journalctl -u alchemy -f | grep "TRADE\|BUY\|SELL\|STOP"
```

### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "bot_running": true,
  "mode": "aggressive",
  "cycle": 42,
  "total_trades": 7,
  "connected_clients": 2,
  "dry_run": true,
  "symbol": "BTCUSD"
}
```

### Monitoring the API in Real-Time

```bash
# Watch portfolio stats every 5 seconds
watch -n 5 'curl -s http://localhost:8000/api/portfolio | python -m json.tool'

# Watch bot status
watch -n 10 'curl -s http://localhost:8000/api/status | python -m json.tool'

# Stream WebSocket messages (requires wscat: npm install -g wscat)
wscat -c ws://localhost:8000/ws
```

---

## 10. Troubleshooting

### Server Won't Start

**`ModuleNotFoundError: No module named 'fastapi'`**
```bash
# Ensure venv is activated
source venv/bin/activate
pip install -r requirements.txt
```

**`anthropic.AuthenticationError`**
```bash
# Check your Anthropic API key in .env
grep ANTHROPIC_API_KEY .env
```

**`Port 8000 already in use`**
```bash
# Find and kill the process
lsof -i :8000
kill -9 <PID>
# Or use a different port
python run_server.py --port 8080
```

---

### WebSocket Not Connecting

1. Ensure the server is running: `curl http://localhost:8000/health`
2. Check browser console for WebSocket errors
3. If behind a proxy, ensure `Upgrade` and `Connection` headers are forwarded
4. The dashboard auto-reconnects every 3 seconds — the red dot in the header indicates disconnected state

---

### Bot Not Placing Orders

**In dry-run mode (expected behaviour)**
Orders are simulated. Check the AI Decision Feed in the dashboard for decisions being made. Switch to live mode when ready:
```bash
# Via API
curl -X POST http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

**In live mode but no orders**
Check the bot state panel — the rejection reason will be shown. Common causes:
- Confidence below threshold (< 0.50)
- Risk:reward below minimum (< 1.5:1)
- Daily loss limit reached
- Max open positions reached
- Geopolitical risk is `critical`

---

### Delta Exchange API Errors

**`401 Unauthorized`**
- Verify `DELTA_API_KEY` and `DELTA_API_SECRET` in `.env`
- Check that the API key has trading permissions on Delta Exchange
- Ensure system clock is synced (HMAC signature uses timestamp)
  ```bash
  timedatectl status        # Check clock sync
  sudo timedatectl set-ntp true
  ```

**`404 Product not found`**
- The symbol may not exist on your Delta Exchange region
- Check available symbols: `curl https://api.india.delta.exchange/v2/products`

---

### Mobile App Can't Connect

**"Network request failed"**
- Use your machine's LAN IP, not `localhost`, for physical devices
- Find your IP: `ip addr show` (Linux) or `ipconfig` (Windows)
- Ensure port 8000 is not blocked by firewall:
  ```bash
  sudo ufw allow 8000
  ```

**WebSocket disconnects immediately**
- Some networks block WebSocket on port 8000
- Try a different port: `python run_server.py --port 8080`
- Or put the server behind HTTPS/WSS (see Nginx section)

---

### High Memory Usage

The server caches news articles, equity curve points (max 2000), and decision history (max 50). If memory is a concern:

```python
# In config.py, reduce caching:
news.fetch_interval_minutes = 30     # Less frequent news refresh
```

---

## 11. Security Checklist

Before going live with real funds:

### API Security
- [ ] Delta Exchange API key has **only** the permissions needed (trading, no withdrawal)
- [ ] API keys are in `.env` file, never committed to git (`.gitignore` covers `.env`)
- [ ] `.env` file permissions are restricted: `chmod 600 .env`

### Network Security
- [ ] Server is not publicly exposed without authentication if running on a VPS
- [ ] Consider adding HTTP Basic Auth or API key to FastAPI if dashboard is public-facing
- [ ] Use HTTPS (TLS) in production — never send API keys over plain HTTP
- [ ] Firewall: only expose required ports (`sudo ufw allow 443; sudo ufw allow 22`)

### Trading Safety
- [ ] Tested thoroughly in **paper trading mode** (`DRY_RUN=true`) before going live
- [ ] `POSITION_SIZE_USD` is set to an amount you are comfortable losing entirely
- [ ] `RISK_PER_TRADE_PCT` is set to 1% or lower for initial live runs
- [ ] `MAX_OPEN_POSITIONS` is set to 1 for initial live runs
- [ ] Telegram notifications are configured so you receive immediate alerts
- [ ] You have verified the bot's decisions make sense over at least 10 paper-trading cycles

### Operational Safety
- [ ] systemd service is configured to restart on failure
- [ ] Log rotation is configured (journalctl handles this by default)
- [ ] You have a plan for what to do if the server goes down mid-trade (Delta Exchange stop losses protect against this)

---

## Appendix: API Quick Reference

```bash
BASE=http://localhost:8000

# Health
curl $BASE/health

# Start bot
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "start", "interval_minutes": 30}'

# Stop bot
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "stop"}'

# Run single cycle
curl -X POST $BASE/api/bot/control -H "Content-Type: application/json" \
  -d '{"action": "cycle"}'

# Toggle dry run
curl -X POST $BASE/api/config -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# Change symbol
curl -X POST $BASE/api/config -H "Content-Type: application/json" \
  -d '{"symbol": "ETHUSD"}'

# Get portfolio
curl $BASE/api/portfolio | python -m json.tool

# Get latest emotion analysis
curl $BASE/api/emotion | python -m json.tool

# Get recent AI decisions
curl "$BASE/api/decisions?limit=10" | python -m json.tool

# Manual trade (bypasses AI)
curl -X POST $BASE/api/trade -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSD", "side": "buy", "size": 0.001, "stop_loss": 93000, "take_profit": 99000}'
```
