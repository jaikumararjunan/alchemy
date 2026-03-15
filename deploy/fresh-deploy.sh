#!/usr/bin/env bash
# =============================================================================
# Alchemy — Fresh Deployment Script
# Run as root on the VPS. Handles everything end-to-end.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/claude/crypto-trading-geopolitical-ai-UsIYY/deploy/fresh-deploy.sh | bash
#
# OR after cloning:
#   bash /opt/alchemy/deploy/fresh-deploy.sh
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/jaikumararjunan/alchemy.git"
BRANCH="claude/crypto-trading-geopolitical-ai-UsIYY"
ALCHEMY_DIR="/opt/alchemy"
DOMAIN="akilamirthya.in"
SERVER_IP="213.199.38.90"
SSL_EMAIL="${SSL_EMAIL:-admin@akilamirthya.in}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${CYAN}══════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════${NC}"; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo bash fresh-deploy.sh"

# ─────────────────────────────────────────────────────────────────────────────
section "1 / 9  System packages"
# ─────────────────────────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq \
    curl wget git ufw fail2ban ca-certificates gnupg lsb-release \
    htop jq python3 python3-pip python3-venv

# ─────────────────────────────────────────────────────────────────────────────
section "2 / 9  Docker"
# ─────────────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    info "Docker installed: $(docker --version)"
else
    info "Docker already present: $(docker --version)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "3 / 9  Firewall"
# ─────────────────────────────────────────────────────────────────────────────
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
info "UFW configured: SSH + 80 + 443 open"

# ─────────────────────────────────────────────────────────────────────────────
section "4 / 9  Stop and clean existing containers"
# ─────────────────────────────────────────────────────────────────────────────
if [[ -f "$ALCHEMY_DIR/docker-compose.prod.yml" ]]; then
    info "Stopping existing prod stack..."
    cd "$ALCHEMY_DIR"
    docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true
fi
if [[ -f "$ALCHEMY_DIR/docker-compose.bootstrap.yml" ]]; then
    cd "$ALCHEMY_DIR"
    docker compose -f docker-compose.bootstrap.yml down --remove-orphans 2>/dev/null || true
fi
docker ps -aq --filter "name=alchemy" | xargs -r docker rm -f 2>/dev/null || true
info "All alchemy containers removed"

# ─────────────────────────────────────────────────────────────────────────────
section "5 / 9  Clone / update repository"
# ─────────────────────────────────────────────────────────────────────────────
if [[ -d "$ALCHEMY_DIR/.git" ]]; then
    info "Updating existing repo..."
    cd "$ALCHEMY_DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    info "Cloning repository..."
    rm -rf "$ALCHEMY_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$ALCHEMY_DIR"
fi
info "Code at: $(git -C $ALCHEMY_DIR log --oneline -1)"

# ─────────────────────────────────────────────────────────────────────────────
section "6 / 9  Environment (.env)"
# ─────────────────────────────────────────────────────────────────────────────
cd "$ALCHEMY_DIR"

if [[ ! -f ".env" ]]; then
    cp .env.example .env
fi

# Check if required keys are still placeholders
NEED_ENV=false
grep -qE "^ANTHROPIC_API_KEY=your_" .env 2>/dev/null && NEED_ENV=true
grep -qE "^DELTA_API_KEY=your_"     .env 2>/dev/null && NEED_ENV=true

if [[ "$NEED_ENV" == "true" ]]; then
    echo ""
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    warn "  API keys not set. Please fill in your .env now."
    warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -rp "  ANTHROPIC_API_KEY: " ANT_KEY
    read -rp "  DELTA_API_KEY:     " DELTA_KEY
    read -rp "  DELTA_API_SECRET:  " DELTA_SECRET
    read -rp "  NEWS_API_KEY (optional, press Enter to skip): " NEWS_KEY

    sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${ANT_KEY}|" .env
    sed -i "s|^DELTA_API_KEY=.*|DELTA_API_KEY=${DELTA_KEY}|"       .env
    sed -i "s|^DELTA_API_SECRET=.*|DELTA_API_SECRET=${DELTA_SECRET}|" .env
    [[ -n "$NEWS_KEY" ]] && sed -i "s|^NEWS_API_KEY=.*|NEWS_API_KEY=${NEWS_KEY}|" .env
    info "API keys written to .env"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "7 / 9  Auth credentials (JWT + TOTP + password)"
# ─────────────────────────────────────────────────────────────────────────────
NEED_AUTH=false
grep -qE "^JWT_SECRET_KEY=\s*$"      .env 2>/dev/null && NEED_AUTH=true
grep -qE "^AUTH_PASSWORD_HASH=\s*$"  .env 2>/dev/null && NEED_AUTH=true

if [[ "$NEED_AUTH" == "true" ]]; then
    info "Installing auth dependencies..."
    pip3 install --quiet --break-system-packages \
        passlib[bcrypt] python-jose[cryptography] pyotp 2>/dev/null || \
    pip3 install --quiet passlib python-jose pyotp 2>/dev/null || true

    echo ""
    warn "Set your dashboard login password:"
    read -rsp "  Dashboard password: " DASH_PASS; echo ""
    read -rsp "  Confirm password:   " DASH_PASS2; echo ""

    if [[ "$DASH_PASS" != "$DASH_PASS2" ]]; then
        error "Passwords do not match"
    fi

    # Generate all secrets via Python
    python3 - "$DASH_PASS" <<'PYEOF'
import sys, secrets, base64
try:
    from passlib.context import CryptContext
    import pyotp
    pwd = sys.argv[1]
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pw_hash   = ctx.hash(pwd)
    jwt_key   = secrets.token_hex(64)
    totp_sec  = pyotp.random_base32()
    # Docker Compose v2 interpolates $VAR inside env_file values.
    # Bcrypt hashes contain literal $ signs ($2b$12$...) which get
    # stripped to empty strings.  Escape every $ as $$ so Compose
    # unescapes them back to $ before the value reaches the container.
    pw_hash_esc = pw_hash.replace("$", "$$")
    with open("/tmp/alchemy_auth", "w") as f:
        f.write(f"AUTH_PASSWORD_HASH={pw_hash_esc}\n")
        f.write(f"JWT_SECRET_KEY={jwt_key}\n")
        f.write(f"TOTP_SECRET={totp_sec}\n")
    print(f"  Password hash:  {pw_hash[:20]}...")
    print(f"  JWT secret:     {jwt_key[:16]}...")
    print(f"  TOTP secret:    {totp_sec[:8]}...")
    # Print QR code URL for Google Authenticator
    otp_uri = pyotp.TOTP(totp_sec).provisioning_uri(name="admin", issuer_name="Alchemy")
    print(f"\n  2FA QR code URI (paste into https://www.qr-code-generator.com/):")
    print(f"  {otp_uri}")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)
PYEOF

    if [[ -f /tmp/alchemy_auth ]]; then
        while IFS='=' read -r key val; do
            # Replace existing key or append
            if grep -q "^${key}=" .env; then
                sed -i "s|^${key}=.*|${key}=${val}|" .env
            else
                echo "${key}=${val}" >> .env
            fi
        done < /tmp/alchemy_auth
        rm -f /tmp/alchemy_auth
        info "Auth credentials written to .env"
    else
        error "Failed to generate auth credentials"
    fi
else
    info "Auth credentials already present — skipping"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "8 / 9  SSL certificate"
# ─────────────────────────────────────────────────────────────────────────────
mkdir -p "$ALCHEMY_DIR/ssl"

if [[ -f "$ALCHEMY_DIR/ssl/live/$DOMAIN/fullchain.pem" ]]; then
    info "SSL cert already exists — skipping certbot"
else
    info "Starting HTTP-only bootstrap stack to obtain SSL cert..."
    docker compose -f docker-compose.bootstrap.yml up -d --build

    info "Waiting for alchemy container to become healthy (up to 3 min)..."
    for i in $(seq 1 36); do
        STATUS=$(docker inspect alchemy --format='{{.State.Health.Status}}' 2>/dev/null || echo "missing")
        if [[ "$STATUS" == "healthy" ]]; then
            info "Alchemy is healthy."
            break
        fi
        echo "  ($i/36) status=$STATUS — waiting..."
        sleep 5
        if [[ $i -eq 36 ]]; then
            warn "Alchemy health check timed out. Showing logs:"
            docker compose -f docker-compose.bootstrap.yml logs alchemy --tail=40
            error "Alchemy failed to start. Fix .env / config and re-run."
        fi
    done

    info "Requesting SSL cert for $DOMAIN..."
    docker compose -f docker-compose.bootstrap.yml run --rm certbot certonly \
        --webroot -w /var/www/certbot \
        -d "$DOMAIN" \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        || { warn "Certbot failed — continuing without SSL (HTTP only)"; }

    info "Stopping bootstrap stack..."
    docker compose -f docker-compose.bootstrap.yml down
fi

# ─────────────────────────────────────────────────────────────────────────────
section "9 / 9  Start production stack"
# ─────────────────────────────────────────────────────────────────────────────

# If SSL cert was NOT obtained, swap nginx to bootstrap config temporarily
if [[ ! -f "$ALCHEMY_DIR/ssl/live/$DOMAIN/fullchain.pem" ]]; then
    warn "No SSL cert — running with HTTP-only nginx (bootstrap config)"
    # Patch prod compose to use bootstrap nginx config on-the-fly
    export NGINX_CONF="./deploy/nginx-bootstrap.conf"
else
    export NGINX_CONF="./deploy/nginx.conf"
fi

info "Building and starting production stack..."
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

info "Waiting for services to stabilise (30s)..."
sleep 30

echo ""
docker compose -f docker-compose.prod.yml ps
echo ""

# ── Health check ──────────────────────────────────────────────────────────────
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:8000/health" 2>/dev/null || echo "000")

echo ""
info "═══════════════════════════════════════"
info "  DEPLOYMENT COMPLETE"
info "═══════════════════════════════════════"
echo ""
echo "  Health check:  HTTP $HTTP_STATUS (should be 200)"
echo ""
if [[ -f "$ALCHEMY_DIR/ssl/live/$DOMAIN/fullchain.pem" ]]; then
echo "  Dashboard:     https://$DOMAIN"
echo "  Direct IP:     http://$SERVER_IP  (redirects to HTTPS)"
else
echo "  Dashboard:     http://$SERVER_IP"
echo "  Domain:        http://$DOMAIN  (SSL pending — re-run after DNS propagation)"
fi
echo ""
echo "  Logs:   docker compose -f $ALCHEMY_DIR/docker-compose.prod.yml logs -f alchemy"
echo "  Stop:   docker compose -f $ALCHEMY_DIR/docker-compose.prod.yml down"
echo "  Status: docker compose -f $ALCHEMY_DIR/docker-compose.prod.yml ps"
echo ""
warn "NOTE: DRY_RUN=true by default. Edit .env to enable live trading."
echo ""
