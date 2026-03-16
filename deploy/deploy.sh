#!/usr/bin/env bash
# =============================================================================
# Alchemy — Blue/Green Production Deploy Script
# =============================================================================
#
# Usage:
#   bash deploy.sh <registry> <image_tag> <dry_run> [git_sha] [actor]
#
# Examples:
#   bash deploy.sh ghcr.io/user/alchemy sha-abc123 false abc123def john
#   bash deploy.sh ghcr.io/user/alchemy v1.2.3    true
#
# Blue/Green Strategy
# -------------------
#  1. Determine the INACTIVE slot (opposite of /opt/alchemy/.active_slot).
#  2. Pull the new image.
#  3. Start the new alchemy container in the inactive slot.
#  4. Wait for Docker health check to pass on the new container.
#  5. Update nginx upstream include to point to the new slot.
#  6. Reload nginx (graceful — zero dropped connections).
#  7. Wait 10 s, then verify the live endpoint is healthy.
#  8. Stop the old slot container.
#  9. Write state files (new active slot, previous image tag for rollback).
# 10. Clean up old/unused images (keep last 3).
#
# On any failure: nginx stays pointing at the previous slot → zero impact.
# =============================================================================
set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
REGISTRY="${1:?Usage: deploy.sh <registry> <image_tag> <dry_run> [sha] [actor]}"
IMAGE_TAG="${2:?Missing image_tag}"
DRY_RUN="${3:-false}"
GIT_SHA="${4:-unknown}"
ACTOR="${5:-ci}"

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_DIR="/opt/alchemy"
SLOT_FILE="${APP_DIR}/.active_slot"
PREV_TAG_FILE="${APP_DIR}/.previous_tag"
UPSTREAM_CONF="${APP_DIR}/upstream.conf"
DEPLOY_LOG="${APP_DIR}/logs/deploy.log"
LOCK_FILE="/tmp/alchemy-deploy.lock"
COMPOSE_PROD="${APP_DIR}/docker-compose.prod.yml"
COMPOSE_BLUE="${APP_DIR}/docker-compose.blue.yml"
COMPOSE_GREEN="${APP_DIR}/docker-compose.green.yml"
IMAGE="${REGISTRY}:${IMAGE_TAG}"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

log()  { echo -e "$(date -u +%H:%M:%S) ${CYAN}[deploy]${NC} $*" | tee -a "$DEPLOY_LOG"; }
ok()   { echo -e "$(date -u +%H:%M:%S) ${GREEN}[✓]${NC} $*"     | tee -a "$DEPLOY_LOG"; }
warn() { echo -e "$(date -u +%H:%M:%S) ${YELLOW}[!]${NC} $*"    | tee -a "$DEPLOY_LOG"; }
fail() { echo -e "$(date -u +%H:%M:%S) ${RED}[✗]${NC} $*"       | tee -a "$DEPLOY_LOG"; exit 1; }

# ── Concurrency lock ──────────────────────────────────────────────────────────
if ! mkdir "$LOCK_FILE" 2>/dev/null; then
  LOCK_PID=$(cat "${LOCK_FILE}/pid" 2>/dev/null || echo "unknown")
  fail "Another deploy is running (PID ${LOCK_PID}). Aborting."
fi
echo $$ > "${LOCK_FILE}/pid"
cleanup() { rm -rf "$LOCK_FILE"; }
trap cleanup EXIT INT TERM

# ── Init ──────────────────────────────────────────────────────────────────────
mkdir -p "${APP_DIR}/logs"
echo "" >> "$DEPLOY_LOG"
log "════════════════════════════════════════════════════════"
log "Deploy started | image=${IMAGE} | dry_run=${DRY_RUN}"
log "Git SHA: ${GIT_SHA} | Actor: ${ACTOR}"
log "════════════════════════════════════════════════════════"

# ── Slot detection ────────────────────────────────────────────────────────────
ACTIVE_SLOT="$(cat "$SLOT_FILE" 2>/dev/null || echo 'blue')"
if [[ "$ACTIVE_SLOT" == "blue" ]]; then
  NEW_SLOT="green"; OLD_SLOT="blue"
else
  NEW_SLOT="blue";  OLD_SLOT="green"
fi

# Compose file for each slot
compose_args_for() {
  local slot="$1"
  local override_file="${APP_DIR}/docker-compose.${slot}.yml"
  echo "-f ${COMPOSE_PROD} -f ${override_file} --project-name alchemy-${slot}"
}

NEW_COMPOSE_ARGS=$(compose_args_for "$NEW_SLOT")
OLD_COMPOSE_ARGS=$(compose_args_for "$OLD_SLOT")
NEW_CONTAINER="alchemy-${NEW_SLOT}"
OLD_CONTAINER="alchemy-${OLD_SLOT}"

log "Active slot: ${ACTIVE_SLOT} → deploying to: ${NEW_SLOT}"

# ── Save current image tag for rollback ───────────────────────────────────────
CURRENT_TAG="$(docker inspect --format '{{index .Config.Image}}' "$OLD_CONTAINER" 2>/dev/null || echo '')"
if [[ -n "$CURRENT_TAG" ]]; then
  echo "$CURRENT_TAG" > "$PREV_TAG_FILE"
  log "Previous image saved: ${CURRENT_TAG}"
fi

# ── Pull new image ────────────────────────────────────────────────────────────
log "Pulling image: ${IMAGE}"
if ! docker pull "$IMAGE"; then
  fail "Failed to pull image ${IMAGE}"
fi
ok "Image pulled"

# ── Start new slot ────────────────────────────────────────────────────────────
log "Starting ${NEW_CONTAINER} ..."
export IMAGE_TAG DRY_RUN
# shellcheck disable=SC2086
if ! docker compose $NEW_COMPOSE_ARGS up -d --force-recreate --remove-orphans alchemy; then
  fail "Failed to start ${NEW_CONTAINER}"
fi

# ── Wait for Docker health check ──────────────────────────────────────────────
log "Waiting for ${NEW_CONTAINER} health check (max 90s)..."
HEALTH_RETRIES=18; HEALTH_DELAY=5
for ((i=1; i<=HEALTH_RETRIES; i++)); do
  STATUS=$(docker inspect --format '{{.State.Health.Status}}' "$NEW_CONTAINER" 2>/dev/null || echo 'starting')
  if [[ "$STATUS" == "healthy" ]]; then
    ok "${NEW_CONTAINER} is healthy (attempt ${i})"
    break
  fi
  if [[ "$STATUS" == "unhealthy" ]]; then
    docker logs --tail=50 "$NEW_CONTAINER" >> "$DEPLOY_LOG" 2>&1 || true
    fail "${NEW_CONTAINER} is unhealthy — aborting deploy"
  fi
  log "  Health: ${STATUS} (${i}/${HEALTH_RETRIES}) — waiting ${HEALTH_DELAY}s..."
  sleep "$HEALTH_DELAY"
  if [[ "$i" -eq "$HEALTH_RETRIES" ]]; then
    docker logs --tail=50 "$NEW_CONTAINER" >> "$DEPLOY_LOG" 2>&1 || true
    fail "Health check timed out for ${NEW_CONTAINER}"
  fi
done

# ── Switch nginx upstream ─────────────────────────────────────────────────────
log "Switching nginx upstream to ${NEW_SLOT} (${NEW_CONTAINER}:8000)..."

# Write new upstream file (nginx includes this in the upstream block)
cat > "$UPSTREAM_CONF" << NGINX_EOF
# Auto-generated by deploy.sh — do not edit manually
# Active slot: ${NEW_SLOT} | Deployed: $(date -u +%Y-%m-%dT%H:%M:%SZ)
server ${NEW_CONTAINER}:8000;
NGINX_EOF

# Reload nginx gracefully (no dropped connections; nginx drains existing)
if docker exec nginx nginx -s reload 2>/dev/null; then
  ok "nginx upstream switched and reloaded"
else
  warn "nginx reload failed — checking if nginx container exists"
  # Fallback: try through compose
  docker compose -f "$COMPOSE_PROD" exec -T nginx nginx -s reload 2>/dev/null || \
    warn "nginx reload skipped (container may not be running yet)"
fi

# ── Post-switch live check ────────────────────────────────────────────────────
log "Waiting 10s for nginx to drain old connections..."
sleep 10

log "Checking live endpoint health..."
LIVE_OK=false
for attempt in 1 2 3 4 5; do
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time 8 --retry 0 \
    http://localhost:8000/health 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    LIVE_OK=true
    ok "Live health check passed (HTTP ${HTTP_CODE}) on attempt ${attempt}"
    break
  fi
  warn "Live check attempt ${attempt}/5 got HTTP ${HTTP_CODE}"
  sleep 5
done

if [[ "$LIVE_OK" != "true" ]]; then
  # Revert nginx to old slot before failing
  warn "Live check failed — reverting nginx to ${OLD_SLOT}"
  cat > "$UPSTREAM_CONF" << REVERT_EOF
# Reverted by deploy.sh after failed health check
server ${OLD_CONTAINER}:8000;
REVERT_EOF
  docker exec nginx nginx -s reload 2>/dev/null || true
  fail "Post-switch health check failed — nginx reverted to ${OLD_SLOT}"
fi

# ── Persist new active slot ───────────────────────────────────────────────────
echo "$NEW_SLOT" > "$SLOT_FILE"
ok "Active slot updated: ${NEW_SLOT}"

# ── Stop old slot ─────────────────────────────────────────────────────────────
log "Stopping old slot: ${OLD_CONTAINER}..."
# shellcheck disable=SC2086
docker compose $OLD_COMPOSE_ARGS stop alchemy 2>/dev/null || \
  docker stop "$OLD_CONTAINER" 2>/dev/null || \
  warn "Old container ${OLD_CONTAINER} not found (first deploy?)"
ok "Old slot stopped"

# ── Image cleanup (keep last 3 tags) ─────────────────────────────────────────
log "Cleaning up old images for ${REGISTRY}..."
docker image ls --format '{{.Repository}}:{{.Tag}} {{.CreatedAt}}' \
  | grep "^${REGISTRY}:" \
  | sort -k2 -r \
  | tail -n +4 \
  | awk '{print $1}' \
  | xargs -r docker rmi 2>/dev/null \
  || true
ok "Image cleanup done"

# ── Summary ───────────────────────────────────────────────────────────────────
log "════════════════════════════════════════════════════════"
ok "Deploy complete"
log "  Active slot  : ${NEW_SLOT}"
log "  Image        : ${IMAGE}"
log "  Git SHA      : ${GIT_SHA}"
log "  DRY_RUN      : ${DRY_RUN}"
log "  Deployed by  : ${ACTOR}"
log "  Timestamp    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "════════════════════════════════════════════════════════"
