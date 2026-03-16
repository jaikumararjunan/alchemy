# CLAUDE.md — Alchemy AI Trading Bot

This file provides context, conventions, and workflows for AI assistants working in this repository.

---

## Project Overview

**Alchemy** is an autonomous AI-powered cryptocurrency trading bot that uses Claude (claude-opus-4-6) as its core decision-making engine. It trades on **Delta Exchange (India)** using a three-layer intelligence system: emotion/sentiment analysis, geopolitical event detection, and technical analysis. The system supports both paper trading (dry-run) and live trading modes.

---

## Repository Structure

```
alchemy/
├── src/                        # Core Python source modules
│   ├── intelligence/           # Claude-powered sentiment + news + geo analysis
│   ├── exchange/               # Delta Exchange REST + WebSocket client
│   ├── strategy/               # Signal generation (combines all intelligence layers)
│   ├── risk/                   # Hard position limits, drawdown controls, R:R enforcement
│   ├── autonomous/             # Claude agent (tool_use loop), portfolio manager, notifier
│   ├── backtest/               # Historical simulation, optimizer, performance metrics
│   ├── derivatives/            # Funding rate, basis, liquidation, options analytics
│   ├── ml/                     # ML models: sentiment, price prediction, anomaly detection
│   ├── scanner/                # Multi-contract opportunity scanner
│   ├── storage/                # SQLite persistence (trades, decisions, equity snapshots)
│   └── utils/                  # Colored logging via colorlog
├── server/
│   └── api.py                  # FastAPI REST API (43KB) — all endpoints
├── dashboard/                  # Single-file vanilla JS web UI
├── mobile/                     # React Native + Expo app (Zustand, react-native-chart-kit)
├── tests/                      # pytest test suite
├── docs/
│   ├── ARCHITECTURE.md         # Full system design (13 sections)
│   ├── DEPLOYMENT.md           # Deployment + operational guide
│   └── diagrams/               # Excalidraw architecture diagrams
├── deploy/                     # Deployment shell scripts
├── .github/workflows/          # CI (ci.yml) and CD (deploy.yml) pipelines
├── config.py                   # Dataclass-based configuration with env var loading
├── main.py                     # Standalone CLI bot entry point (no web server)
├── run_server.py               # Server + bot entry point
├── Dockerfile                  # Multi-stage production image (non-root user `alchemy`)
├── docker-compose.yml          # Development compose (hot-reload)
├── docker-compose.prod.yml     # Production compose
├── Makefile                    # All development and production task shortcuts
├── requirements.txt            # Python dependencies (35 packages)
└── .env.example                # Environment variable template
```

---

## Key Files to Understand First

| File | Why It Matters |
|------|---------------|
| `config.py` | Central configuration — all env vars, trading params, thresholds |
| `src/autonomous/ai_orchestrator.py` | Core Claude tool_use agent loop (44KB) — primary intelligence |
| `src/strategy/trading_strategy.py` | Signal generation combining all three intelligence layers (25KB) |
| `src/risk/risk_manager.py` | Hard risk enforcement — never bypassed (14KB) |
| `server/api.py` | All REST endpoints, background tasks, WebSocket management (43KB) |
| `docs/ARCHITECTURE.md` | Definitive system design reference |

---

## Development Commands

All common tasks are in the `Makefile`. Prefer `make` commands over manual invocations.

### Setup
```bash
make install        # Install production dependencies
make install-dev    # Install dev + test dependencies
make setup-env      # Copy .env.example to .env
```

### Running Locally
```bash
make dev            # Docker compose up (hot-reload, foreground)
make dev-bg         # Docker compose up (background)
make dev-bot        # Run bot in Docker without web server
make paper          # Run paper trading (Python directly, no Docker)
make cycle          # Run single trading cycle
```

### Direct Entry Points
```bash
python run_server.py --dry-run --start-bot   # Server + bot (paper trade)
python main.py --dry-run --symbol BTCUSD     # Standalone bot (no web)
```

### Code Quality
```bash
make lint           # Run ruff linter
make lint-fix       # Auto-fix lint issues
make type-check     # Run mypy type checking
make test           # Run pytest
make test-cov       # Run pytest with coverage report
```

### Docker
```bash
make build          # Build dev image
make build-prod     # Build production image
make stop           # Stop all containers
make logs           # Tail container logs
make shell          # Open shell inside container
```

### Production
```bash
make prod           # Start production stack
make prod-restart   # Restart production services
make prod-status    # Check production health
make deploy         # Trigger GitHub Actions deploy
```

### Monitoring
```bash
make health         # API health check
make watch          # Watch logs in real-time
make ws             # Connect to WebSocket
```

---

## Configuration System

Configuration uses Python dataclasses in `config.py`. All values load from environment variables with sensible defaults.

**Main config classes:**
- `DeltaConfig` — Delta Exchange API credentials, symbol whitelist, leverage limits
- `AnthropicConfig` — Claude model name, API key
- `NewsConfig` — RSS feed URLs, geo risk keywords
- `TradingConfig` — Risk thresholds, position sizing, signal weights
- `AppConfig` — Top-level aggregator, calls `config.validate()` on startup

**Required environment variables** (see `.env.example`):
```bash
DELTA_API_KEY=...
DELTA_API_SECRET=...
ANTHROPIC_API_KEY=...
TELEGRAM_BOT_TOKEN=...      # optional, for alerts
TELEGRAM_CHAT_ID=...        # optional
DRY_RUN=true                # always start with this enabled
```

**Never hardcode** credentials or secrets. Always use `os.getenv()` or the config dataclass pattern.

---

## Code Conventions

### Python Style
- **Full type hints** on all function signatures — enforced by mypy in CI
- **snake_case** for functions and variables
- **CamelCase** for classes
- **UPPER_CASE** for module-level constants
- **Dataclasses** with `@dataclass` and `field()` for structured data
- **Docstrings** on all public classes and non-trivial functions

### Logging
Every module creates its logger at the top of the file:
```python
from src.utils.logger import get_logger
logger = get_logger(__name__)
```
Never use `print()` for operational output — always use the logger.

### Async Patterns
- FastAPI routes use `async def` with `await`
- Background tasks use `asyncio` directly
- WebSocket connections use `websocket-client` (sync) in separate threads
- Never mix sync blocking calls inside `async def` without `run_in_executor`

### Error Handling
- Raise `ValueError` from `config.validate()` for missing required config
- Use structured logging at `logger.error(...)` with context before raising
- Do not swallow exceptions silently — always log the error at minimum

### Intelligence Layer Weights
The signal weights are defined in `TradingConfig` and must sum to 1.0:
- Emotion intelligence (Claude sentiment): **45%**
- Geopolitical analysis: **25%**
- Technical analysis (RSI, MACD, Bollinger Bands): **30%**

Changing these weights requires re-validating the strategy logic in `src/strategy/trading_strategy.py`.

---

## Testing

Tests live in `tests/`. Run with `make test` or `pytest`.

### Conventions
- Use **pytest fixtures** for database/store setup
- Use **in-memory SQLite** (`:memory:`) — never a real file in tests
- Use `pytest-asyncio` for async test functions
- Mark slow tests with `@pytest.mark.slow` if applicable
- Aim for coverage on all storage and strategy logic

### CI Matrix
Tests run on Python **3.10, 3.11, and 3.12** in GitHub Actions. Ensure code is compatible with all three versions.

---

## CI/CD Pipelines

### CI (`ci.yml`) — runs on every push/PR
1. **Lint** — `ruff` checks all Python files
2. **Test** — `pytest` on Python 3.10, 3.11, 3.12 matrix with codecov upload
3. **Docker Build** — verifies the image builds successfully

### CD (`deploy.yml`) — runs on push to `main`/`master` or manual dispatch
1. Build and push Docker image to registry (cached via `buildcache`)
2. SSH to deploy host, copy compose files, run `deploy/deploy.sh`
3. Health check the deployed service
4. Notify Slack on success or failure

**Secrets required in GitHub:** `DELTA_API_KEY`, `DELTA_API_SECRET`, `ANTHROPIC_API_KEY`, `DOCKER_REGISTRY`, `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `SLACK_WEBHOOK_URL`

---

## Architecture Summary

### Intelligence Pipeline (per trading cycle)
```
News RSS Feeds → GeoAnalyzer (keyword scoring) → EmotionEngine (Claude claude-opus-4-6)
                                                          ↓
                                              Sentiment + Geo Score (70%)
                                                          ↓
                                     + Technical Indicators (30%)
                                                          ↓
                                            TradingStrategy.generate_signal()
                                                          ↓
                                            RiskManager.validate_trade()
                                                          ↓
                                            DeltaClient.place_order() [if approved]
```

### AI Orchestrator (Claude Tool Use)
`src/autonomous/ai_orchestrator.py` runs a **tool_use agentic loop** where Claude:
- Calls tools to fetch market data, news, portfolio state
- Decides whether to enter/exit positions
- Writes reasoning to `decisions` table in SQLite for full audit trail

The orchestrator uses `claude-opus-4-6` model. Do not downgrade the model without benchmarking signal quality.

### Risk Manager (Critical — Never Bypass)
`src/risk/risk_manager.py` enforces hard limits independent of AI decisions:
- Max daily loss limit
- Max drawdown threshold
- Max open positions count
- Minimum risk-reward ratio
- Position sizing constraints

**Never disable or bypass risk checks** — these are the last line of defense in live trading.

### Storage Layer
SQLite database (`storage/`) with three tables:
- `trade_log` — all executed trades
- `decisions` — Claude's reasoning for each cycle
- `equity_snapshots` — periodic portfolio snapshots for drawdown calculation

---

## Mobile App (`mobile/`)

React Native + Expo 51 app. Key dependencies: Zustand (state), react-native-chart-kit (charts).

```bash
cd mobile
npm install
npx expo start       # Development server
npx expo build       # Production build
```

The mobile app connects to the FastAPI server. Configure `API_BASE_URL` in `mobile/src/config.ts`.

---

## Common Development Tasks

### Adding a New Trading Symbol
1. Add symbol to `DeltaConfig.symbol_whitelist` in `config.py`
2. Verify Delta Exchange contract ID in `src/exchange/delta_client.py`
3. Add any symbol-specific parameters to `TradingConfig`
4. Test with `DRY_RUN=true` before enabling live trading

### Adding a New Intelligence Source
1. Create a new module in `src/intelligence/`
2. Add a new weight to `TradingConfig` (ensure all weights sum to 1.0)
3. Update `src/strategy/trading_strategy.py` to incorporate the new signal
4. Add corresponding tool in `src/autonomous/ai_orchestrator.py` if Claude should call it
5. Write tests in `tests/`

### Adding a New API Endpoint
1. Add route to `server/api.py` using FastAPI `APIRouter` or directly on `app`
2. Use `async def` for all route handlers
3. Add Pydantic models for request/response validation
4. Update `dashboard/` if the endpoint needs a UI

### Modifying Risk Parameters
- All thresholds are in `TradingConfig` in `config.py`
- Override via environment variables — never hardcode values
- Always test changes with `DRY_RUN=true` and review `decisions` table output

---

## Safety Notes for AI Assistants

1. **Always default to dry-run** — Set `DRY_RUN=true` when testing any trading logic changes.
2. **Do not modify risk_manager.py limits** without explicit instruction — these protect real capital.
3. **Do not change Claude model** in `AnthropicConfig` without benchmarking — signal quality is model-sensitive.
4. **Do not commit `.env` files** — only `.env.example` belongs in git.
5. **Validate config changes** — after modifying `config.py`, run `python -c "from config import AppConfig; AppConfig()"` to ensure validation passes.
6. **Type safety** — mypy runs in CI; ensure new code passes `make type-check` before committing.
7. **Test storage changes carefully** — the SQLite schema affects historical data integrity; use migrations if changing table structure.
