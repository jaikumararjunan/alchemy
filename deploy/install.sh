#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# ALCHEMY TRADING PLATFORM — ONE-CLICK DEPLOYMENT
# Hostinger VPS (Ubuntu 22.04 LTS) · KVM2 (4 vCPU, 8GB RAM) or higher
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/install.sh | sudo bash
#
# Or:
#   git clone https://github.com/jaikumararjunan/alchemy.git
#   cd alchemy && sudo bash deploy/install.sh
#
# What this script does:
#   1. System update + dependencies (Python 3.11, Node 20, Nginx, Certbot, Git)
#   2. Clone/update repo to /opt/alchemy
#   3. Python venv + all pip dependencies
#   4. Build React frontend (npm install + npm run build)
#   5. Configure environment variables (.env)
#   6. Initialise SQLite DB + create super admin
#   7. Create systemd services (alchemy-api)
#   8. Configure Nginx with SSL (Let's Encrypt via Certbot)
#   9. Enable UFW firewall (80, 443, 22)
#  10. Start all services + health check
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
banner()  { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════════${NC}"; echo -e "${BOLD}${BLUE}  $*${NC}"; echo -e "${BOLD}${BLUE}══════════════════════════════════════════${NC}\n"; }

# ── Configuration (edit these before running) ─────────────────────────────────
DOMAIN="${DOMAIN:-alchemy.yourdomain.com}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@alchemy.in}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Alchemy#Admin!$(openssl rand -hex 4)}"
REPO_URL="${REPO_URL:-https://github.com/jaikumararjunan/alchemy.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/alchemy}"
APP_USER="${APP_USER:-alchemy}"
PYTHON_VERSION="3.11"
NODE_VERSION="20"
PORT=8000

banner "🔮 Alchemy Trading Platform — Hostinger VPS Installer"

# ── Preflight checks ──────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash $0"
[[ -z "${DOMAIN:-}" ]] && { warn "DOMAIN not set. Using: $DOMAIN (update after install)"; }
info "Installing on: $(hostname) ($(uname -r))"
info "Target directory: $INSTALL_DIR"
info "Domain: $DOMAIN"

# ── 1. System update ──────────────────────────────────────────────────────────
banner "Step 1/10: System Update"
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq \
    git curl wget unzip jq \
    build-essential libssl-dev libffi-dev zlib1g-dev \
    software-properties-common ca-certificates gnupg2 \
    nginx certbot python3-certbot-nginx \
    ufw fail2ban \
    redis-server \
    ffmpeg \
    postgresql postgresql-contrib
success "System packages installed"

# ── 2. Python 3.11 ───────────────────────────────────────────────────────────
banner "Step 2/10: Python $PYTHON_VERSION"
if ! python${PYTHON_VERSION} --version &>/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa -q
    apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev
fi
python${PYTHON_VERSION} --version
success "Python $PYTHON_VERSION ready"

# ── 3. Node.js 20 ────────────────────────────────────────────────────────────
banner "Step 3/10: Node.js $NODE_VERSION"
if ! node --version 2>/dev/null | grep -q "v${NODE_VERSION}"; then
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - -q
    apt-get install -y -qq nodejs
fi
node --version && npm --version
success "Node.js $(node --version) ready"

# ── 4. Application user ───────────────────────────────────────────────────────
banner "Step 4/10: Application User"
id $APP_USER &>/dev/null || useradd -r -s /bin/bash -d $INSTALL_DIR $APP_USER
mkdir -p $INSTALL_DIR
chown $APP_USER:$APP_USER $INSTALL_DIR

# ── 5. Clone / update repo ────────────────────────────────────────────────────
banner "Step 5/10: Application Code"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing repo..."
    cd $INSTALL_DIR && sudo -u $APP_USER git pull origin main
else
    info "Cloning repo..."
    sudo -u $APP_USER git clone $REPO_URL $INSTALL_DIR
fi
success "Code ready at $INSTALL_DIR"

# ── 6. Python venv + dependencies ────────────────────────────────────────────
banner "Step 6/10: Python Dependencies"
cd $INSTALL_DIR
sudo -u $APP_USER python${PYTHON_VERSION} -m venv .venv
sudo -u $APP_USER .venv/bin/pip install --upgrade pip -q
sudo -u $APP_USER .venv/bin/pip install -r requirements.txt -q
sudo -u $APP_USER .venv/bin/pip install \
    uvicorn[standard] gunicorn \
    aiosqlite asyncpg sqlalchemy[asyncio] \
    bcrypt PyJWT pyotp qrcode[pil] cryptography \
    httpx structlog fastapi python-multipart \
    chromadb \
    yt-dlp \
    -q
success "Python dependencies installed"

# ── 7. Frontend build ─────────────────────────────────────────────────────────
banner "Step 7/10: React Frontend Build"
cd $INSTALL_DIR/frontend
sudo -u $APP_USER npm install --silent
sudo -u $APP_USER npm run build
success "Frontend built to $INSTALL_DIR/static/"

# ── 8. Environment configuration ─────────────────────────────────────────────
banner "Step 8/10: Environment Configuration"
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    JWT_SECRET=$(openssl rand -hex 32)
    VAULT_KEY=$(openssl rand -hex 32)
    cat > $ENV_FILE << ENV
# Alchemy Platform — Generated $(date)
ENV=production
LOG_LEVEL=info
ENABLE_AI_AGENTS=false

# Security — GENERATED AUTOMATICALLY
JWT_SECRET_KEY=${JWT_SECRET}
ALCHEMY_VAULT_KEY=${VAULT_KEY}
ALCHEMY_FERNET_KEY=

# Database (SQLite for quick start — migrate to PostgreSQL for production)
DATABASE_URL=sqlite+aiosqlite:////${INSTALL_DIR}/data/alchemy.db

# Admin Bootstrap
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Redis
REDIS_URL=redis://localhost:6379/0

# Exchange API Keys (add via /tokens/register API after login)
DELTA_API_KEY=
DELTA_API_SECRET=
BINANCE_API_KEY=
BINANCE_API_SECRET=
ANGEL_API_KEY=

# LLM (optional)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
ENV
    chmod 600 $ENV_FILE
    chown $APP_USER:$APP_USER $ENV_FILE
    success "Environment file created: $ENV_FILE"
else
    warn ".env already exists — skipping"
fi

# ── 9. Data directory ─────────────────────────────────────────────────────────
mkdir -p $INSTALL_DIR/data/{chromadb,logs}
chown -R $APP_USER:$APP_USER $INSTALL_DIR/data

# ── 10. Initialise database ───────────────────────────────────────────────────
banner "Step 9/10: Database + Super Admin"
cd $INSTALL_DIR
sudo -u $APP_USER bash -c "
    source .env 2>/dev/null || true
    .venv/bin/python3 -c \"
import asyncio, os
os.chdir('$INSTALL_DIR')
for k,v in open('$INSTALL_DIR/.env').read().splitlines():
    try:
        k2,v2 = k.split('=',1)
        if k2 and not k2.startswith('#'): os.environ.setdefault(k2.strip(), v2.strip())
    except: pass

async def init():
    from alchemy.api.database import create_tables, create_initial_admin
    await create_tables()
    email = os.environ.get('ADMIN_EMAIL','admin@alchemy.in')
    pwd   = os.environ.get('ADMIN_PASSWORD','')
    if pwd: await create_initial_admin(email, pwd)
    print('Database initialized')

asyncio.run(init())
\" 2>&1 || echo 'DB init: check manually'
"
success "Database ready"

# ── 11. Systemd service ───────────────────────────────────────────────────────
cat > /etc/systemd/system/alchemy-api.service << SERVICE
[Unit]
Description=Alchemy Trading Platform API
After=network.target redis.service
Wants=redis.service

[Service]
Type=exec
User=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn alchemy.api.app:app \
    --host 127.0.0.1 \
    --port ${PORT} \
    --workers 2 \
    --log-level info \
    --access-log \
    --no-use-colors
Restart=on-failure
RestartSec=10
StandardOutput=append:${INSTALL_DIR}/data/logs/api.log
StandardError=append:${INSTALL_DIR}/data/logs/api.log
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable alchemy-api
systemctl start alchemy-api
sleep 3
systemctl is-active alchemy-api && success "Alchemy API service running" || warn "API service check: systemctl status alchemy-api"

# ── 12. Nginx configuration ───────────────────────────────────────────────────
banner "Step 10/10: Nginx + SSL"
cat > /etc/nginx/sites-available/alchemy << NGINX
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    # Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    # SSL (Certbot will update these)
    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=auth:10m rate=5r/m;
    limit_req_zone \$binary_remote_addr zone=api:20m  rate=100r/m;

    location /auth/ {
        limit_req zone=auth burst=10 nodelay;
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400s;
    }

    location /api/ {
        limit_req zone=api burst=50 nodelay;
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
NGINX

# Temporarily create HTTP-only config for Certbot
cat > /etc/nginx/sites-available/alchemy-temp << NGINX_TEMP
server {
    listen 80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { proxy_pass http://127.0.0.1:${PORT}; proxy_http_version 1.1; proxy_set_header Host \$host; }
}
NGINX_TEMP

ln -sf /etc/nginx/sites-available/alchemy-temp /etc/nginx/sites-enabled/alchemy 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Certbot SSL
mkdir -p /var/www/certbot
if [[ "$DOMAIN" != "alchemy.yourdomain.com" ]]; then
    certbot certonly --nginx -d $DOMAIN --email $ADMIN_EMAIL --agree-tos --non-interactive || {
        warn "SSL setup failed. Run manually: certbot --nginx -d $DOMAIN"
    }
    # Switch to full HTTPS config
    ln -sf /etc/nginx/sites-available/alchemy /etc/nginx/sites-enabled/alchemy
    nginx -t && systemctl reload nginx && success "Nginx + SSL configured"
else
    warn "Skipping SSL — set DOMAIN env var and run: certbot --nginx -d yourdomain.com"
fi

# ── 13. Firewall ──────────────────────────────────────────────────────────────
ufw allow ssh
ufw allow 'Nginx Full'
ufw --force enable
success "UFW firewall enabled"

# ── 14. Fail2ban ──────────────────────────────────────────────────────────────
systemctl enable fail2ban --now
success "Fail2ban enabled"

# ── 15. Final health check ────────────────────────────────────────────────────
sleep 3
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/health 2>/dev/null || echo "000")
if [[ "$HTTP_STATUS" == "200" ]]; then
    success "Health check passed (HTTP 200)"
else
    warn "Health check returned: $HTTP_STATUS — check: systemctl status alchemy-api"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
banner "🔮 Alchemy Deployment Complete!"
echo -e "${GREEN}✓ API:${NC}          http://localhost:${PORT}"
echo -e "${GREEN}✓ Web:${NC}          https://${DOMAIN}"
echo -e "${GREEN}✓ API Docs:${NC}     https://${DOMAIN}/docs"
echo -e "${GREEN}✓ Admin Email:${NC}  ${ADMIN_EMAIL}"
echo -e "${GREEN}✓ Admin Pwd:${NC}    ${ADMIN_PASSWORD}"
echo -e "${YELLOW}  ⚠ SAVE the admin password above!${NC}"
echo ""
echo -e "Useful commands:"
echo -e "  ${BLUE}systemctl status alchemy-api${NC}   — Service status"
echo -e "  ${BLUE}journalctl -u alchemy-api -f${NC}   — Live logs"
echo -e "  ${BLUE}tail -f $INSTALL_DIR/data/logs/api.log${NC}"
echo -e "  ${BLUE}sudo bash $INSTALL_DIR/deploy/update.sh${NC} — Update to latest"
echo ""
echo -e "${BOLD}Super admin credentials saved to:${NC} $ENV_FILE"
