# ─────────────────────────────────────────────────────────────────────────────
# Alchemy Trading Platform — Makefile
#
# Usage:
#   make up        → Build + start everything (first run)
#   make dev       → Start with hot-reload frontend dev server
#   make down      → Stop all containers
#   make logs      → Tail API logs
#   make restart   → Restart API without rebuild
#   make rebuild   → Force full image rebuild
#   make shell     → Open shell inside API container
#   make test      → Run unit tests inside container
#   make reset     → Wipe all data and start fresh
# ─────────────────────────────────────────────────────────────────────────────

COMPOSE        = docker compose -f docker-compose.local.yml
COMPOSE_DEV    = $(COMPOSE) --profile dev
IMAGE          = alchemy:local
CONTAINER      = alchemy-api

.PHONY: up dev down logs restart rebuild shell test reset status clean help

# ── Default ───────────────────────────────────────────────────────────────────
.DEFAULT_GOAL := help

help:  ## Show this help
	@echo ""
	@echo "🔮  Alchemy Trading Platform — Docker Commands"
	@echo "════════════════════════════════════════════════"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Quick start:"
	@echo "    make up    → http://localhost:8000"
	@echo "    make dev   → http://localhost:8000 + http://localhost:3000 (hot reload)"
	@echo ""

# ── Build & Start ─────────────────────────────────────────────────────────────
up: ## Build images + start API + Redis (access at http://localhost:8000)
	@echo "🔨 Building Alchemy..."
	$(COMPOSE) up --build -d
	@echo ""
	@echo "✅ Alchemy is starting up..."
	@echo "   API + Frontend : http://localhost:8000"
	@echo "   API Docs       : http://localhost:8000/docs"
	@echo "   Login          : admin@alchemy.in / Alchemy#Admin!2024"
	@echo ""
	@echo "   Waiting for health check..."
	@sleep 5 && $(COMPOSE) ps

dev: ## Start with hot-reload frontend (Node dev server at :3000, API at :8000)
	@echo "🔨 Starting dev stack (API + React hot-reload)..."
	$(COMPOSE_DEV) up --build -d
	@echo ""
	@echo "✅ Dev stack started:"
	@echo "   API + Backend  : http://localhost:8000"
	@echo "   React Dev UI   : http://localhost:3000  ← use this for development"
	@echo "   API Docs       : http://localhost:8000/docs"
	@echo ""

# ── Control ───────────────────────────────────────────────────────────────────
down: ## Stop all containers
	$(COMPOSE_DEV) down
	@echo "✅ All containers stopped"

restart: ## Restart API container (no rebuild)
	$(COMPOSE) restart api
	@echo "✅ API restarted"

rebuild: ## Force full rebuild of images
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d
	@echo "✅ Rebuilt and restarted"

# ── Monitoring ────────────────────────────────────────────────────────────────
logs: ## Tail API logs (Ctrl+C to stop)
	$(COMPOSE) logs -f api

logs-all: ## Tail all container logs
	$(COMPOSE_DEV) logs -f

status: ## Show container status + resource usage
	@$(COMPOSE_DEV) ps
	@echo ""
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
		$$($(COMPOSE_DEV) ps -q 2>/dev/null) 2>/dev/null || true

health: ## Check API health
	@curl -s http://localhost:8000/health | python3 -m json.tool

# ── Development ───────────────────────────────────────────────────────────────
shell: ## Open bash shell inside API container
	docker exec -it $(CONTAINER) bash

shell-redis: ## Open redis-cli
	docker exec -it alchemy-redis redis-cli

test: ## Run unit tests inside the API container
	docker exec $(CONTAINER) python3 -m pytest tests/unit/ -v --no-cov -q

# ── Data management ───────────────────────────────────────────────────────────
reset: ## ⚠️  Wipe all data (DB, vault, ChromaDB) and restart fresh
	@echo "⚠️  This will DELETE all data (database, users, trades)."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	$(COMPOSE_DEV) down -v
	$(COMPOSE) up --build -d
	@echo "✅ Fresh start complete. Admin: admin@alchemy.in / Alchemy#Admin!2024"

backup: ## Backup SQLite database to ./backups/
	@mkdir -p backups
	@docker cp $(CONTAINER):/app/data/alchemy.db backups/alchemy_$(shell date +%Y%m%d_%H%M%S).db
	@echo "✅ Database backed up to backups/"

clean: ## Remove stopped containers + dangling images
	docker compose -f docker-compose.local.yml down --remove-orphans 2>/dev/null || true
	docker image prune -f
	@echo "✅ Cleaned up"
