# =============================================================================
# Alchemy — Developer Makefile
# Usage: make <target>
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help dev prod build stop logs shell lint test clean deploy

# ── Variables ─────────────────────────────────────────────────────────────────
IMAGE      ?= alchemy
TAG        ?= latest
COMPOSE    ?= docker compose
COMPOSE_PROD ?= docker compose -f docker-compose.prod.yml

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Development ───────────────────────────────────────────────────────────────
dev: ## Start development server (paper trading, hot-reload)
	$(COMPOSE) up

dev-bg: ## Start development server in background
	$(COMPOSE) up -d

dev-bot: ## Start dev server + auto-start bot
	$(COMPOSE) run --rm alchemy python run_server.py --host 0.0.0.0 --port 8000 --dry-run --start-bot --reload

paper: ## Run paper trading bot directly (no Docker)
	python run_server.py --dry-run --start-bot

cycle: ## Run one analysis cycle (paper)
	python main.py --dry-run --symbol BTCUSD

# ── Docker ────────────────────────────────────────────────────────────────────
build: ## Build Docker image
	docker build -t $(IMAGE):$(TAG) .

build-prod: ## Build production Docker image (no cache)
	docker build --no-cache -t $(IMAGE):$(TAG) .

stop: ## Stop all containers
	$(COMPOSE) down

stop-prod: ## Stop production containers
	$(COMPOSE_PROD) down

logs: ## Follow dev logs
	$(COMPOSE) logs -f

logs-prod: ## Follow production logs
	$(COMPOSE_PROD) logs -f alchemy

shell: ## Open shell inside running dev container
	$(COMPOSE) exec alchemy bash

# ── Production ────────────────────────────────────────────────────────────────
prod: ## Start full production stack
	$(COMPOSE_PROD) up -d

prod-pull: ## Pull latest images and restart production
	$(COMPOSE_PROD) pull
	$(COMPOSE_PROD) up -d --no-deps --remove-orphans alchemy

prod-restart: ## Restart alchemy service only (zero-downtime)
	$(COMPOSE_PROD) up -d --no-deps alchemy

prod-status: ## Show production service status
	$(COMPOSE_PROD) ps
	@echo ""
	@curl -sf http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "Health check failed"

# ── Code Quality ──────────────────────────────────────────────────────────────
lint: ## Run ruff lint + format check
	ruff check .
	ruff format --check .

lint-fix: ## Auto-fix lint issues
	ruff check --fix .
	ruff format .

type-check: ## Run mypy type checker
	mypy src/ server/ --ignore-missing-imports

test: ## Run test suite
	pytest tests/ -v

test-cov: ## Run tests with coverage report
	pytest tests/ -v --cov=src --cov=server --cov-report=html --cov-report=term-missing

# ── Setup ─────────────────────────────────────────────────────────────────────
install: ## Install Python dependencies
	pip install -r requirements.txt

install-dev: ## Install dev dependencies
	pip install -r requirements.txt ruff mypy pytest pytest-asyncio pytest-cov

setup-env: ## Copy .env.example to .env
	cp -n .env.example .env || true
	@echo "Edit .env and add your API keys"

# ── Monitoring ────────────────────────────────────────────────────────────────
health: ## Quick health check
	@curl -sf http://localhost:8000/health | python3 -m json.tool

watch: ## Watch portfolio stats (refreshes every 5s)
	watch -n 5 'curl -s http://localhost:8000/api/portfolio | python3 -m json.tool'

ws: ## Connect to WebSocket stream (requires wscat: npm i -g wscat)
	wscat -c ws://localhost:8000/ws

# ── Deployment ────────────────────────────────────────────────────────────────
deploy: ## Trigger GitHub Actions deploy (requires gh CLI)
	gh workflow run deploy.yml

server-setup: ## Run production server setup script (requires SSH + sudo)
	ssh -t $(DEPLOY_USER)@$(DEPLOY_HOST) "sudo bash -s" < deploy/setup.sh

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean: ## Remove build artifacts and __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f coverage.xml .coverage

clean-docker: ## Remove local Docker images and volumes
	$(COMPOSE) down -v --rmi local
	docker image prune -f
