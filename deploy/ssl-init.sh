#!/usr/bin/env bash
# =============================================================================
# Alchemy — SSL Bootstrap Script
# Run on the VPS after the repo is cloned and .env is filled in.
#
# Usage:
#   cd /opt/alchemy
#   bash deploy/ssl-init.sh
# =============================================================================
set -euo pipefail

DOMAIN="akilamirthya.in"
EMAIL="${SSL_EMAIL:-admin@akilamirthya.in}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

cd "$DIR"

# ── 1. Check .env is filled in ───────────────────────────────────────────────
if grep -q "your_anthropic_api_key_here" .env 2>/dev/null; then
    error ".env still has placeholder values. Fill in your API keys first:\n  nano $DIR/.env"
fi

# ── 2. Start bootstrap stack (HTTP only, no SSL needed) ──────────────────────
info "Starting bootstrap stack (HTTP only)..."
docker compose -f docker-compose.bootstrap.yml up -d --build

info "Waiting for alchemy to become healthy..."
for i in $(seq 1 24); do
    if docker inspect alchemy --format='{{.State.Health.Status}}' 2>/dev/null | grep -q healthy; then
        info "Alchemy is healthy."
        break
    fi
    echo "  ($i/24) waiting..."
    sleep 5
done

if ! docker inspect alchemy --format='{{.State.Health.Status}}' 2>/dev/null | grep -q healthy; then
    warn "Alchemy did not become healthy in time. Showing logs:"
    docker compose -f docker-compose.bootstrap.yml logs alchemy --tail=30
    error "Fix the alchemy startup errors, then re-run this script."
fi

# ── 3. Issue SSL cert ─────────────────────────────────────────────────────────
info "Requesting SSL certificate for $DOMAIN..."
mkdir -p "$DIR/ssl"

docker compose -f docker-compose.bootstrap.yml run --rm certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email

info "SSL cert issued successfully."

# ── 4. Switch to full prod stack ─────────────────────────────────────────────
info "Stopping bootstrap stack..."
docker compose -f docker-compose.bootstrap.yml down

info "Starting full production stack (HTTP + HTTPS)..."
docker compose -f docker-compose.prod.yml up -d --build

info "Waiting for services..."
sleep 20
docker compose -f docker-compose.prod.yml ps

echo ""
info "=== Done! ==="
echo ""
echo "  HTTP  → http://$DOMAIN          (redirects to HTTPS)"
echo "  HTTPS → https://$DOMAIN"
echo "  IP    → http://213.199.38.90    (HTTP, for direct IP access)"
echo ""
echo "  Login at: https://$DOMAIN"
echo "  Monitor:  docker compose -f docker-compose.prod.yml logs -f alchemy"
echo ""
warn "SSL cert auto-renews via the certbot container in the prod stack."
