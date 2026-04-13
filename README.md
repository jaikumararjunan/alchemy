# 🔮 Alchemy — AI Trading Platform

[![Version](https://img.shields.io/badge/version-0.8.0-blue)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-152%20passing-green)](tests/)
[![Python](https://img.shields.io/badge/python-3.12-blue)](requirements.local.txt)
[![License](https://img.shields.io/badge/license-proprietary-red)](#)

**Production:** https://akilamirthya.in

AI-powered algorithmic trading platform connecting Binance, Delta Exchange, Angel Broking, and Zerodha Kite — with real-time charts, ML strategy generation, emotional intelligence engine, and single-click VPS deployment.

---

## Quick Start

```bash
git clone https://github.com/jaikumararjunan/alchemy.git && cd alchemy
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.local.txt
cd frontend && npm install && npm run build && cd ..
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Open http://localhost:8000 · Login: `admin@alchemy.in` / `Alchemy#Admin!2024`

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **End-to-end architecture** — 18 sections covering system, data flows, security, deployment |
| [CLAUDE.md](CLAUDE.md) | AI assistant context — read first before any changes |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Complete deployment guide with version details |
| [CHANGELOG.md](CHANGELOG.md) | Version history and upgrade notes |
| [SETUP_NOTIFICATIONS.md](SETUP_NOTIFICATIONS.md) | Gmail, Telegram, WhatsApp setup |
| [RESEARCH.md](RESEARCH.md) | Enhancement roadmap from world-class research |

## Architecture

```
Backend:  FastAPI 0.115 + Python 3.12 (async throughout)
Frontend: React 18 + Vite 5 + TailwindCSS (mobile-first)
Database: SQLite (dev) / PostgreSQL (prod) via SQLAlchemy async
Auth:     JWT + bcrypt-12 + TOTP 2FA + Email OTP
Deploy:   Docker + Nginx + Let's Encrypt + Systemd
Monitor:  Prometheus + Grafana + Alertmanager
```

## Features

- **4 Exchanges:** Binance, Delta Exchange, Angel Broking, Zerodha Kite
- **Real-time Charts:** SVG candlestick with RSI, MACD, BB, EMA indicators  
- **AI Strategies:** Scalping, Momentum, Breakout, News-Driven
- **Emotional Intelligence:** Fear & Greed index with 5 market regimes
- **Watchlist:** Personal symbol tracking with notes and target prices  ← *new*
- **Price Alerts:** Above/below threshold alerts with notification dispatch  ← *new*
- **CVaR Risk Metrics:** Expected Shortfall + Kelly Criterion position sizing  ← *new*
- **Security:** AES-256-GCM vault, 2FA enforcement, credential stuffing detection
- **Alerts:** Telegram, WhatsApp, Gmail notifications
- **Admin Panel:** User management, audit logs, subscription control
- **Subscription Plans:** Free / Pro ₹2,999 / Team ₹9,999 / Enterprise

## Security

- All exchange API keys encrypted with AES-256-GCM
- TOTP 2FA required for exchange credential management
- Credential stuffing detection (>20 login attempts = block)
- Complete audit log of all user actions
- Rate limiting per endpoint (production) with dev bypass

## Tests

```bash
python3 -m pytest tests/unit/ --no-cov -q
# 152 passed
```
