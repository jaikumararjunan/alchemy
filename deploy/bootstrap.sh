#!/usr/bin/env bash
# =============================================================================
# Alchemy — One-Command Bootstrap for Contabo VPS
# Run as root on a fresh Ubuntu 22.04 LTS server.
#
# Usage (run directly on server as root):
#   curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/bootstrap.sh | bash
#
# OR copy this file to server and run:
#   bash bootstrap.sh
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/jaikumararjunan/alchemy.git"
BRANCH="claude/crypto-trading-geopolitical-ai-UsIYY"
ALCHEMY_DIR="/opt/alchemy"
DOMAIN="akilamirthya.in"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo bash bootstrap.sh"

info "=== Alchemy Bootstrap — akilamirthya.in ==="

# ── 1. System packages ────────────────────────────────────────────────────────
info "Updating system..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq git curl wget ufw fail2ban ca-certificates gnupg lsb-release htop jq python3 python3-pip python3-venv

# ── 2. Docker ─────────────────────────────────────────────────────────────────
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

# ── 3. Clone / update repo ────────────────────────────────────────────────────
if [[ -d "$ALCHEMY_DIR/.git" ]]; then
    info "Pulling latest code..."
    git -C "$ALCHEMY_DIR" fetch origin "$BRANCH"
    git -C "$ALCHEMY_DIR" reset --hard "origin/$BRANCH"
else
    info "Cloning repository..."
    git clone --branch "$BRANCH" "$REPO_URL" "$ALCHEMY_DIR"
fi

# ── 4. Python dependencies (needed for auth setup script) ─────────────────────
info "Installing Python dependencies for auth setup..."
pip3 install --quiet pyotp passlib[bcrypt] python-jose[cryptography] qrcode 2>/dev/null || \
    pip3 install --quiet --break-system-packages pyotp passlib python-jose qrcode

# ── 5. .env setup ─────────────────────────────────────────────────────────────
if [[ ! -f "$ALCHEMY_DIR/.env" ]]; then
    warn ".env not found — copying from template"
    cp "$ALCHEMY_DIR/.env.example" "$ALCHEMY_DIR/.env"
    warn "IMPORTANT: Edit $ALCHEMY_DIR/.env and add your API keys before starting!"
    warn "  nano $ALCHEMY_DIR/.env"
else
    info ".env already exists — skipping"
fi

# ── 6. Auth credentials setup ─────────────────────────────────────────────────
if grep -qE "^(JWT_SECRET_KEY=|TOTP_SECRET=)$" "$ALCHEMY_DIR/.env" 2>/dev/null || \
   ! grep -q "JWT_SECRET_KEY" "$ALCHEMY_DIR/.env" 2>/dev/null; then
    info "Generating auth credentials..."
    cd "$ALCHEMY_DIR"
    # Generate credentials non-interactively using Python
    python3 - <<'PYEOF'
import sys, os, secrets
sys.path.insert(0, "/opt/alchemy")
try:
    from src.auth.auth_manager import AuthManager
    jwt_secret = AuthManager.generate_jwt_secret()
    totp_secret = AuthManager.generate_totp_secret()
    # Write to a temp file for bash to source
    with open("/tmp/alchemy_auth_secrets", "w") as f:
        f.write(f"JWT_SECRET_KEY={jwt_secret}\n")
        f.write(f"TOTP_SECRET={totp_secret}\n")
    print(f"  JWT secret:  {jwt_secret[:16]}... (generated)")
    print(f"  TOTP secret: {totp_secret[:8]}... (generated)")
except Exception as e:
    print(f"  Warning: Could not generate secrets automatically: {e}")
    print("  Run: python3 /opt/alchemy/scripts/setup_auth.py manually")
PYEOF

    if [[ -f /tmp/alchemy_auth_secrets ]]; then
        # Append generated secrets to .env (if not already set)
        grep -q "JWT_SECRET_KEY=" "$ALCHEMY_DIR/.env" || \
            cat /tmp/alchemy_auth_secrets >> "$ALCHEMY_DIR/.env"
        rm -f /tmp/alchemy_auth_secrets
        warn "Auth secrets added to .env. Set AUTH_PASSWORD_HASH by running:"
        warn "  cd $ALCHEMY_DIR && python3 scripts/setup_auth.py"
    fi
else
    info "Auth credentials already present in .env"
fi

# ── 7. Firewall ───────────────────────────────────────────────────────────────
info "Configuring UFW..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 8. Fail2ban ───────────────────────────────────────────────────────────────
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
[sshd]
enabled = true
EOF
systemctl enable --now fail2ban

# ── 9. Kernel tuning ─────────────────────────────────────────────────────────
grep -q "alchemy network tuning" /etc/sysctl.conf || cat >> /etc/sysctl.conf <<'EOF'

# alchemy network tuning
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
EOF
sysctl -p

# ── 10. systemd service ───────────────────────────────────────────────────────
cat > /etc/systemd/system/alchemy.service <<EOF
[Unit]
Description=Alchemy AI Trading Bot
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$ALCHEMY_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker compose -f docker-compose.prod.yml pull && /usr/bin/docker compose -f docker-compose.prod.yml up -d --remove-orphans
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable alchemy

# ── 11. SSL dirs ──────────────────────────────────────────────────────────────
mkdir -p "$ALCHEMY_DIR/ssl"

# ── 12. Start (skip if .env still has placeholder) ────────────────────────────
if grep -q "your_anthropic_api_key_here" "$ALCHEMY_DIR/.env"; then
    echo ""
    warn "=========================================================="
    warn "  .env still has placeholder values — NOT starting yet.   "
    warn "  Fill in your API keys:                                   "
    warn "    nano $ALCHEMY_DIR/.env                                 "
    warn "  Then start with:                                         "
    warn "    systemctl start alchemy                                "
    warn "=========================================================="
else
    info "Starting Alchemy stack..."
    cd "$ALCHEMY_DIR"
    docker compose -f docker-compose.prod.yml up -d --build
    info "Stack started. Checking health..."
    sleep 15
    docker compose -f docker-compose.prod.yml ps
fi

echo ""
info "=== Bootstrap complete ==="
echo ""
echo "  Server:   213.199.38.90"
echo "  Domain:   $DOMAIN"
echo "  App dir:  $ALCHEMY_DIR"
echo ""
echo "  Next steps:"
echo "  1. Point DNS A record:  akilamirthya.in → 213.199.38.90"
echo "  2. Edit .env:           nano $ALCHEMY_DIR/.env"
echo "     Required: ANTHROPIC_API_KEY, DELTA_API_KEY, DELTA_API_SECRET"
echo "  3. Set auth password:   cd $ALCHEMY_DIR && python3 scripts/setup_auth.py"
echo "     (adds AUTH_PASSWORD_HASH, QR code for Google Authenticator)"
echo "  4. Start stack:         systemctl start alchemy"
echo "  5. Get SSL cert:        cd $ALCHEMY_DIR && docker compose -f docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --email admin@$DOMAIN --agree-tos --no-eff-email"
echo "  6. Restart nginx:       docker compose -f docker-compose.prod.yml restart nginx"
echo "  7. Monitor:             docker compose -f docker-compose.prod.yml logs -f alchemy"
echo ""
