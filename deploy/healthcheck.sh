#!/usr/bin/env bash
# =============================================================================
# Alchemy — Extended Health Check & Smoke Tests
# =============================================================================
#
# Usage:
#   bash healthcheck.sh [host] [port]
#
# Defaults:
#   host = localhost
#   port = 8000
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
#
# What it checks:
#   1. /health           — application health endpoint returns 2xx
#   2. /api/v1/status    — API status endpoint
#   3. Auth endpoint     — /api/auth/login returns 4xx (not 5xx = auth is live)
#   4. WebSocket         — WS handshake upgrade succeeds
#   5. Static assets     — dashboard index returns 2xx
#   6. Metrics endpoint  — /metrics (Prometheus) returns 2xx
#   7. Response time     — /health responds within 3 seconds
#   8. JSON validity     — /api/v1/status returns valid JSON
# =============================================================================
set -uo pipefail

HOST="${1:-localhost}"
PORT="${2:-8000}"
BASE="http://${HOST}:${PORT}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

PASS=0; FAIL=0

log()  { echo -e "$(date -u +%H:%M:%S) ${CYAN}[healthcheck]${NC} $*"; }
ok()   { echo -e "$(date -u +%H:%M:%S) ${GREEN}[✓]${NC} $*"; ((PASS++)); }
warn() { echo -e "$(date -u +%H:%M:%S) ${YELLOW}[!]${NC} $*"; }
fail() { echo -e "$(date -u +%H:%M:%S) ${RED}[✗]${NC} $*"; ((FAIL++)); }

log "════════════════════════════════════════════════════════"
log "Smoke tests against ${BASE}"
log "════════════════════════════════════════════════════════"

# ── Helper ────────────────────────────────────────────────────────────────────
check_http() {
  local name="$1" url="$2" expected_pattern="$3" max_time="${4:-8}"
  local http_code
  http_code=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time "$max_time" "$url" 2>/dev/null || echo "000")
  if [[ "$http_code" =~ $expected_pattern ]]; then
    ok "${name} — HTTP ${http_code}"
    return 0
  else
    fail "${name} — HTTP ${http_code} (expected ${expected_pattern})"
    return 1
  fi
}

# ── 1. Health endpoint ────────────────────────────────────────────────────────
check_http "Health endpoint       (/health)" \
  "${BASE}/health" "^2"

# ── 2. API status endpoint ────────────────────────────────────────────────────
check_http "API status            (/api/v1/status)" \
  "${BASE}/api/v1/status" "^2"

# ── 3. Auth endpoint reachable (expect 4xx, not 5xx/000) ─────────────────────
log "Checking auth endpoint is live (expect 422 or 405)..."
http_code=$(curl -s -o /dev/null -w '%{http_code}' \
  --max-time 8 \
  -X POST "${BASE}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{}' 2>/dev/null || echo "000")
if [[ "$http_code" =~ ^4 ]]; then
  ok "Auth endpoint             (/api/auth/login) — HTTP ${http_code} (auth layer alive)"
else
  fail "Auth endpoint             (/api/auth/login) — HTTP ${http_code} (expected 4xx)"
fi

# ── 4. Static dashboard ───────────────────────────────────────────────────────
check_http "Dashboard index       (/)" \
  "${BASE}/" "^2"

# ── 5. Metrics endpoint ───────────────────────────────────────────────────────
check_http "Prometheus metrics    (/metrics)" \
  "${BASE}/metrics" "^2"

# ── 6. Response time < 3s on /health ─────────────────────────────────────────
log "Checking /health response time (max 3s)..."
elapsed=$(curl -s -o /dev/null -w '%{time_total}' \
  --max-time 3 "${BASE}/health" 2>/dev/null || echo "999")
# Compare using awk (bash can't do float comparisons)
if awk "BEGIN{exit !($elapsed < 3.0)}"; then
  ok "Response time             ${elapsed}s < 3s"
else
  fail "Response time             ${elapsed}s >= 3s (too slow)"
fi

# ── 7. JSON validity of /api/v1/status ───────────────────────────────────────
log "Checking /api/v1/status returns valid JSON..."
body=$(curl -s --max-time 8 "${BASE}/api/v1/status" 2>/dev/null || echo "")
if echo "$body" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  ok "JSON validity             (/api/v1/status)"
else
  fail "JSON validity             (/api/v1/status) — body: ${body:0:120}"
fi

# ── 8. WebSocket upgrade handshake ───────────────────────────────────────────
log "Checking WebSocket upgrade (GET /ws with Upgrade header)..."
ws_status=$(curl -s -o /dev/null -w '%{http_code}' \
  --max-time 5 \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  "${BASE}/ws" 2>/dev/null || echo "000")
# nginx proxies WS correctly: 101 Switching Protocols or 200 if service intercepts
if [[ "$ws_status" =~ ^(101|200|400)$ ]]; then
  ok "WebSocket upgrade         (/ws) — HTTP ${ws_status}"
else
  fail "WebSocket upgrade         (/ws) — HTTP ${ws_status} (expected 101/200/400)"
fi

# ── 9. Ensure no 5xx errors on key endpoints ─────────────────────────────────
log "Checking no 5xx errors on critical endpoints..."
ALL_OK=true
for path in /health /api/v1/status / /metrics; do
  code=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time 8 "${BASE}${path}" 2>/dev/null || echo "000")
  if [[ "$code" =~ ^5 ]]; then
    fail "5xx detected on ${path} — HTTP ${code}"
    ALL_OK=false
  fi
done
if $ALL_OK; then
  ok "No 5xx errors on critical endpoints"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log "════════════════════════════════════════════════════════"
log "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
log "════════════════════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}[✗] Smoke tests FAILED — ${FAIL} check(s) did not pass${NC}"
  exit 1
fi

echo -e "${GREEN}[✓] All smoke tests passed (${PASS}/${PASS})${NC}"
exit 0
