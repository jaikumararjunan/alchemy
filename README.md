# 🔮 Alchemy — AI-Powered Algorithmic Trading Platform

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://github.com/jaikumararjunan/alchemy/actions/workflows/ci.yml/badge.svg)](https://github.com/jaikumararjunan/alchemy/actions)

> Production-grade, AI-native algorithmic trading platform integrating the full QuantInsti open-source ecosystem with LangGraph multi-agent orchestration, LiteLLM-powered LLM routing, and institutional-quality analytics.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ALCHEMY PLATFORM                          │
│                                                             │
│  Presentation ── React Dashboard  │  pyfolio Tear Sheets    │
│  AI Agents    ── LangGraph        │  LiteLLM Gateway        │
│  Strategy     ── Blueshift SDK    │  Zipline Pipeline       │
│  Analytics    ── pyfolio + ARCH   │  quantrautil Data       │
│  Execution    ── IB Controller    │  Kite Connect (NSE)     │
└─────────────────────────────────────────────────────────────┘
```

## Modules

| Module | QuantInsti Source | Purpose |
|--------|------------------|---------|
| `alchemy/agents` | AI-in-Trading-Workflow | LangGraph multi-agent orchestration |
| `alchemy/llm` | litellm (fork) | Unified LLM gateway (Claude/GPT/Gemini) |
| `alchemy/strategy` | blueshift-developer-kit | Strategy factory + templates |
| `alchemy/pipeline` | zipline-pipeline | Factor-based universe screening |
| `alchemy/analytics` | pyfolio + arch | Portfolio analytics + volatility |
| `alchemy/data` | quantrautil | Market data adapter (NSE/US) |
| `alchemy/execution` | ib-controller + kiteconnect3 | Broker execution gateways |
| `alchemy/risk` | Live-Algo-Trading-Setups | Risk management engine |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/jaikumararjunan/alchemy.git
cd alchemy

# 2. Setup environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml with your API keys

# 4. Start LiteLLM Gateway
python -m alchemy.llm.gateway --port 4000

# 5. Run agent (paper mode)
python -m alchemy.agents.run --ticker RELIANCE --mode paper
```

## UML Architecture Diagrams

All diagrams are in [`docs/uml/`](docs/uml/).

| Diagram | Description |
|---------|-------------|
| [System Context](docs/uml/01_system_context.png) | C4 L1 — Alchemy in ecosystem |
| [Component Architecture](docs/uml/02_component_architecture.png) | C4 L2 — Five-layer decomposition |
| [Sequence Diagram](docs/uml/03_sequence_diagram.png) | AI agent trade lifecycle |
| [Class Diagram](docs/uml/04_class_diagram.png) | Core integration classes |
| [Integration Matrix](docs/uml/05_integration_architecture.png) | Module-wise mapping |
| [Migration Roadmap](docs/uml/06_migration_roadmap.png) | 10-week phased plan |
| [Deployment Architecture](docs/uml/07_deployment.png) | AWS cloud deployment |

## Migration Document

See [`docs/migration/`](docs/migration/) for the full Alchemy ← QuantInsti migration specification.

## License

Apache 2.0 — See [LICENSE](LICENSE)

## v0.2 — Frontend + Crypto Update

### New: React Dashboard (`frontend/`)
Full-featured trading dashboard built with React 18 + Vite + Tailwind CSS:
- **Dashboard** — Live NAV chart, AI signal feed, crypto snapshot, risk footer
- **Crypto Trading** — Delta Exchange + Binance order form, positions table, funding rates
- **Portfolio** — Asset allocation pie, daily P&L bar chart, positions table
- **AI Signals** — Agent runner + full signal history
- **Risk Manager** — Emergency stop controls, drawdown monitor
- **Analytics** — Cumulative returns vs benchmark, Sharpe/Sortino/Calmar metrics
- **Strategy Library** — Browse and backtest strategies

```bash
cd frontend && npm install && npm run dev   # → http://localhost:3000
```

### New: Crypto Execution (`alchemy/execution/crypto/`)

| Gateway | File | Exchange |
|---------|------|----------|
| `DeltaGateway` | `delta_gateway.py` | Delta Exchange — BTC/ETH perpetuals, options, MOVE |
| `BinanceGateway` | `binance_gateway.py` | Binance — Spot + USD-M Futures + COIN-M |

Both gateways support **paper trading mode** (default) — no real API keys needed for development.
