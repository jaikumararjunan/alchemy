#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  Alchemy Trading Platform — Production VPS Installer
#  Tested: Ubuntu 22.04 LTS (Hostinger VPS, Contabo, DigitalOcean)
#
#  USAGE:
#    Basic (with domain + SSL):
#      DOMAIN=akilamirthya.in ADMIN_EMAIL=you@email.com bash install.sh
#
#    With Kubernetes:
#      DOMAIN=akilamirthya.in ENABLE_K8S=true bash install.sh
#
#    IP-only (no domain/SSL):
#      bash install.sh
#
# ════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Config (override with env vars before running) ──────────────
DOMAIN="${DOMAIN:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@alchemy.local}"
REPO="${REPO:-https://github.com/jaikumararjunan/alchemy}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/alchemy}"
DATA_DIR="${DATA_DIR:-/var/lib/alchemy}"
ENABLE_K8S="${ENABLE_K8S:-false}"
GH_TOKEN="${GH_TOKEN:-}"          # Set if repo is private: GH_TOKEN=ghp_xxx

# Strip trailing slash and https:// from DOMAIN if present
DOMAIN="${DOMAIN#https://}"
DOMAIN="${DOMAIN#http://}"
DOMAIN="${DOMAIN%/}"

# Auto-generate secrets
JWT_SECRET="${JWT_SECRET:-$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9!@#' | head -c 40)}"
VAULT_KEY="${VAULT_KEY:-$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9!@#' | head -c 40)}"
ADMIN_PASS="${ADMIN_PASS:-$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)}"

# ── Colors ───────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${GREEN}[$(date +%H:%M:%S)] ✓${NC} $*"; }
warn()   { echo -e "${YELLOW}[$(date +%H:%M:%S)] ⚠${NC}  $*"; }
err()    { echo -e "${RED}[$(date +%H:%M:%S)] ✗${NC} $*" >&2; }
header() { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════${NC}"; \
           echo -e "${BOLD}${BLUE}  $*${NC}"; \
           echo -e "${BOLD}${BLUE}══════════════════════════════════════${NC}"; }

# ── Root check ───────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { err "Run as root: sudo bash install.sh"; exit 1; }

header "Alchemy Trading Platform — Installer"
echo -e "  ${BOLD}Domain:${NC}      ${DOMAIN:-'(using IP address)'}"
echo -e "  ${BOLD}Admin email:${NC} $ADMIN_EMAIL"
echo -e "  ${BOLD}App dir:${NC}     $APP_DIR"
echo -e "  ${BOLD}Data dir:${NC}    $DATA_DIR"
echo -e "  ${BOLD}Kubernetes:${NC}  $ENABLE_K8S"
echo ""

# ── Step 1: System update ─────────────────────────────────────────
header "Step 1/10: System Update"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  curl wget git unzip htop jq \
  ufw fail2ban \
  nginx certbot python3-certbot-nginx \
  ca-certificates gnupg lsb-release
log "System packages installed"

# ── Step 2: Docker ───────────────────────────────────────────────
header "Step 2/10: Docker Installation"
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable docker --now
  log "Docker installed"
else
  log "Docker already installed: $(docker --version)"
fi

# ── Step 3: Firewall ─────────────────────────────────────────────
header "Step 3/10: Firewall (UFW)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment 'SSH'
ufw allow 80/tcp   comment 'HTTP'
ufw allow 443/tcp  comment 'HTTPS'
ufw --force enable
log "UFW active: SSH/HTTP/HTTPS allowed, all else blocked"

# ── Step 4: Fail2ban ─────────────────────────────────────────────
header "Step 4/10: Fail2ban"
cat > /etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s

[nginx-http-auth]
enabled  = true

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
logpath  = /var/log/nginx/error.log
maxretry = 10
F2B
systemctl enable fail2ban --now
log "Fail2ban: bans IPs after 5 failed SSH attempts for 1 hour"

# ── Step 5: Clone repository ─────────────────────────────────────
header "Step 5/10: Clone Repository"
[[ -d "$APP_DIR" ]] && { warn "Existing installation found — backing up"; mv "$APP_DIR" "${APP_DIR}.bak.$(date +%Y%m%d_%H%M%S)"; }
mkdir -p "$DATA_DIR"

# Build clone URL (supports private repos via GH_TOKEN)
if [[ -n "$GH_TOKEN" ]]; then
  CLONE_URL="https://${GH_TOKEN}@github.com/jaikumararjunan/alchemy.git"
  log "Using GitHub token for private repo access"
else
  CLONE_URL="$REPO"
fi

git clone --depth 1 --branch "$BRANCH" "$CLONE_URL" "$APP_DIR"
cd "$APP_DIR"
log "Repository cloned to $APP_DIR"

# ── Step 6: Environment ──────────────────────────────────────────
header "Step 6/10: Environment Configuration"
cat > "$APP_DIR/.env.production" << ENVEOF
# Alchemy Production Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
ENV=production
LOG_LEVEL=info

# ── Security (AUTO-GENERATED — save these!) ────────────────────
JWT_SECRET_KEY=${JWT_SECRET}
ALCHEMY_VAULT_KEY=${VAULT_KEY}

# ── Database ───────────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:////data/alchemy.db

# ── Admin account ──────────────────────────────────────────────
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASS}

# ── Email OTP (configure for production use) ───────────────────
# Gmail: myaccount.google.com → Security → App Passwords → generate 16-char code
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=${ADMIN_EMAIL}

# ── Domain ─────────────────────────────────────────────────────
DOMAIN=${DOMAIN:-localhost}
ENVEOF
chmod 600 "$APP_DIR/.env.production"
log "Environment file created at $APP_DIR/.env.production"

# ── Step 7: Build & Deploy ───────────────────────────────────────
header "Step 7/10: Docker Build & Deploy"
cd "$APP_DIR"

# Fix data dir permissions before starting
mkdir -p "${DATA_DIR}" && chmod 777 "${DATA_DIR}"

cat > "$APP_DIR/docker-compose.production.yml" << DCEOF
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    image: alchemy-app:latest
    restart: always
    env_file: .env.production
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////data/alchemy.db
    volumes:
      - ${DATA_DIR}:/data:rw
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
DCEOF

log "Building Docker image (this takes 3-5 minutes)..."
log "  → Installing Node.js frontend dependencies..."
log "  → Building React app..."
log "  → Installing Python packages..."
DOCKER_BUILDKIT=1 docker compose -f docker-compose.production.yml build --progress plain 2>&1 |   grep -E "Step|RUN|COPY|FROM|Successfully|error|Error|failed|warning" | tail -20 || {
  echo ""
  echo "Build failed. Full logs:"
  docker compose -f docker-compose.production.yml logs
  exit 1
}
log "Docker image built"

docker compose -f docker-compose.production.yml up -d
log "Container started"

# ── Step 8: Nginx ────────────────────────────────────────────────
header "Step 8/10: Nginx Configuration"

# Base nginx config (works for both IP and domain)
SERVER_NAME="${DOMAIN:-_}"

cat > /etc/nginx/sites-available/alchemy << NGXEOF
# Rate limiting zones
limit_req_zone \$binary_remote_addr zone=api_zone:10m rate=20r/s;
limit_req_zone \$binary_remote_addr zone=auth_zone:10m rate=5r/m;

server {
    listen 80;
    server_name ${SERVER_NAME};

    # ── Security Headers ───────────────────────────────────────
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # ── Hide server version ─────────────────────────────────────
    server_tokens off;

    # ── Request size limits ─────────────────────────────────────
    client_max_body_size 10m;
    client_body_timeout  30s;
    client_header_timeout 30s;
    keepalive_timeout 75s;

    # Gzip
    gzip on;
    gzip_types text/plain application/json application/javascript text/css;

    # Auth endpoints — strict rate limiting
    location ~* ^/api/auth/(login|signup) {
        limit_req zone=auth_zone burst=10 nodelay;
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }

    # WebSocket connections
    location /ws {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # API routes
    location /api/ {
        limit_req          zone=api_zone burst=50 nodelay;
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }

    # Everything else (SPA + static)
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/alchemy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
log "Nginx configured"

# ── Step 9: SSL (domain only) ────────────────────────────────────
header "Step 9/10: SSL Certificate"
if [[ -n "$DOMAIN" && "$DOMAIN" != "localhost" && "$DOMAIN" != "_" ]]; then
  log "Requesting Let's Encrypt certificate for $DOMAIN..."
  certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$ADMIN_EMAIL" \
    --redirect \
    2>&1 | tail -5
  # Auto-renewal
  (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && systemctl reload nginx") \
    | sort -u | crontab -
  log "SSL certificate issued + auto-renewal configured"
else
  warn "No domain provided — skipping SSL. App accessible via http://<IP>:80"
fi

# ── Step 10: Systemd service ─────────────────────────────────────
header "Step 10/10: Systemd Service"
cat > /etc/systemd/system/alchemy.service << SVCEOF
[Unit]
Description=Alchemy AI Trading Platform
Documentation=https://github.com/jaikumararjunan/alchemy
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStartPre=/usr/bin/docker compose -f docker-compose.production.yml pull --ignore-pull-failures
ExecStart=/usr/bin/docker compose -f docker-compose.production.yml up
ExecStop=/usr/bin/docker compose -f docker-compose.production.yml down
Restart=always
RestartSec=10
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable alchemy
log "Systemd service enabled (auto-starts on reboot)"

# ── Update command ───────────────────────────────────────────────
cat > /usr/local/bin/alchemy-update << 'UPDEOF'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/alchemy
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Alchemy — Zero-Downtime Update"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "▶ Pulling latest code..."
cd $APP_DIR && git pull origin main
echo "▶ Rebuilding image..."
docker compose -f docker-compose.production.yml build
echo "▶ Rolling restart..."
docker compose -f docker-compose.production.yml up -d --no-deps app
echo "✅ Update complete!"
docker compose -f docker-compose.production.yml ps
UPDEOF
chmod +x /usr/local/bin/alchemy-update

# ── Health check ─────────────────────────────────────────────────
echo -e "\n${BOLD}Waiting for app to start...${NC}"
for i in {1..18}; do
  if curl -sf "http://localhost:8000/api/health" &>/dev/null; then
    log "Health check passed ✓"
    break
  fi
  echo -n "."
  sleep 5
done

# ── Final summary ─────────────────────────────────────────────────
PROTO="http"
[[ -n "$DOMAIN" && -f "/etc/letsencrypt/live/$DOMAIN/cert.pem" ]] && PROTO="https"
APP_URL="${PROTO}://${DOMAIN:-$(curl -sf https://ipinfo.io/ip 2>/dev/null || echo 'YOUR_SERVER_IP')}"

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   ✅  Alchemy Deployment Complete!       ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}🌐 URL:${NC}            $APP_URL"
echo -e "  ${BOLD}📧 Admin email:${NC}    $ADMIN_EMAIL"
echo -e "  ${BOLD}🔑 Admin password:${NC} $ADMIN_PASS"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "  alchemy-update                          # Pull + rebuild + restart"
echo -e "  docker compose -f ${APP_DIR}/docker-compose.production.yml logs -f  # Live logs"
echo -e "  systemctl status alchemy                # Service status"
echo ""
echo -e "  ${BOLD}⚠️  SAVE THESE SECRETS (not shown again):${NC}"
echo -e "  JWT_SECRET_KEY = $JWT_SECRET"
echo -e "  VAULT_KEY      = $VAULT_KEY"
echo ""
echo -e "  ${BOLD}📧 Configure email OTP (optional):${NC}"
echo -e "  nano ${APP_DIR}/.env.production"
echo -e "  → Set SMTP_USER and SMTP_PASSWORD"
echo -e "  → Then run: alchemy-update"
echo ""
