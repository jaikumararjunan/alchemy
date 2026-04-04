#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
#  Alchemy Trading Platform — Single-Click VPS Installer
#  Tested: Ubuntu 22.04 LTS (Hostinger VPS, Contabo VPS)
#  Usage:
#    DOMAIN=alchemy.yourdomain.com bash install.sh
#    OR: curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/install.sh | bash
# ════════════════════════════════════════════════════════════════
set -euo pipefail
IFS=$'\n\t'

# ── Config (override with env vars) ──────────────────────────────
DOMAIN="${DOMAIN:-alchemy.$(curl -sf https://ipinfo.io/ip 2>/dev/null).nip.io}"
REPO="${REPO:-https://github.com/jaikumararjunan/alchemy}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/alchemy}"
DATA_DIR="${DATA_DIR:-/var/lib/alchemy}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9!@#$%^&*' | head -c40)}"
VAULT_KEY="${VAULT_KEY:-$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9!@#$%^&*' | head -c40)}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@${DOMAIN}}"
ADMIN_PASS="${ADMIN_PASS:-$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c16)}"
ENABLE_K8S="${ENABLE_K8S:-false}"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()   { echo -e "${GREEN}[$(date +%H:%M:%S)] ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}[$(date +%H:%M:%S)] ⚠${NC}  $*"; }
error() { echo -e "${RED}[$(date +%H:%M:%S)] ✗${NC} $*" >&2; }
info()  { echo -e "${BLUE}[$(date +%H:%M:%S)] ℹ${NC} $*"; }
header(){ echo -e "\n${BOLD}${BLUE}══ $* ══${NC}"; }

check_root() {
  [[ $EUID -eq 0 ]] || { error "Run as root: sudo bash install.sh"; exit 1; }
}

header "Alchemy Trading Platform Installer"
check_root

echo -e "${BOLD}Domain:${NC}     $DOMAIN"
echo -e "${BOLD}Admin:${NC}      $ADMIN_EMAIL"
echo -e "${BOLD}App dir:${NC}    $APP_DIR"
echo -e "${BOLD}K8s mode:${NC}   $ENABLE_K8S"
echo ""

# ── 1. System update ─────────────────────────────────────────────
header "System Update"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  curl wget git unzip htop \
  ufw fail2ban \
  nginx certbot python3-certbot-nginx \
  docker.io docker-compose-v2
log "System packages installed"

# ── 2. Firewall ───────────────────────────────────────────────────
header "Firewall Setup"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"
ufw --force enable
log "UFW firewall configured"

# ── 3. Fail2ban ───────────────────────────────────────────────────
cat > /etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
logpath  = /var/log/nginx/error.log
maxretry = 10
F2B
systemctl enable fail2ban --now
log "Fail2ban configured"

# ── 4. Docker ─────────────────────────────────────────────────────
header "Docker Setup"
systemctl enable docker --now
if [[ "$ENABLE_K8S" == "true" ]]; then
  # Install k3s (lightweight Kubernetes)
  header "Kubernetes (k3s)"
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik" sh -
  export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  # Install ingress-nginx
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.4/deploy/static/provider/cloud/deploy.yaml
  # Install cert-manager
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
  log "k3s Kubernetes installed"
fi

# ── 5. Clone repo ─────────────────────────────────────────────────
header "Cloning Repository"
[[ -d "$APP_DIR" ]] && rm -rf "$APP_DIR"
git clone --depth 1 --branch "$BRANCH" "$REPO" "$APP_DIR"
mkdir -p "$DATA_DIR"
cd "$APP_DIR"
log "Repository cloned"

# ── 6. Environment file ───────────────────────────────────────────
header "Environment Configuration"
cat > "$APP_DIR/.env.production" << ENVEOF
ENV=production
LOG_LEVEL=info

# Security (auto-generated — SAVE THESE!)
JWT_SECRET_KEY=${JWT_SECRET}
ALCHEMY_VAULT_KEY=${VAULT_KEY}

# Database
DATABASE_URL=sqlite+aiosqlite:////${DATA_DIR}/alchemy.db

# Admin
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASS}

# Email OTP (configure your SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=${ADMIN_EMAIL}

# Optional: Redis for distributed rate limiting
# REDIS_URL=redis://localhost:6379/0
ENVEOF
chmod 600 "$APP_DIR/.env.production"
log "Environment file created"

# ── 7. Build & Start (Docker) ─────────────────────────────────────
if [[ "$ENABLE_K8S" != "true" ]]; then
  header "Docker Build & Deploy"
  cd "$APP_DIR"

  # Build image
  docker build -t alchemy-app:latest . 2>&1 | tail -5
  log "Docker image built"

  # docker-compose.production.yml
  cat > "$APP_DIR/docker-compose.production.yml" << DCEOF
version: '3.9'
services:
  app:
    image: alchemy-app:latest
    restart: always
    env_file: .env.production
    volumes:
      - ${DATA_DIR}:/data
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD","curl","-f","http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
DCEOF

  docker compose -f docker-compose.production.yml up -d
  log "Docker containers started"

# ── 7b. Kubernetes Deploy ─────────────────────────────────────────
else
  header "Kubernetes Deploy"
  # Build and load image into k3s
  docker build -t alchemy-app:latest .
  docker save alchemy-app:latest | k3s ctr images import -

  # Apply manifests
  sed -i "s/alchemy.yourdomain.com/$DOMAIN/g" deploy/k8s/ingress.yaml

  kubectl apply -f deploy/k8s/namespace.yaml
  kubectl apply -f deploy/k8s/pvc.yaml

  # Create secret from env file
  kubectl create secret generic alchemy-secrets \
    --from-literal=JWT_SECRET_KEY="$JWT_SECRET" \
    --from-literal=ALCHEMY_VAULT_KEY="$VAULT_KEY" \
    --from-literal=ADMIN_PASSWORD="$ADMIN_PASS" \
    --from-literal=SMTP_USER="" \
    --from-literal=SMTP_PASSWORD="" \
    -n alchemy --dry-run=client -o yaml | kubectl apply -f -

  kubectl apply -f deploy/k8s/deployment.yaml
  kubectl apply -f deploy/k8s/service.yaml
  kubectl apply -f deploy/k8s/ingress.yaml
  kubectl apply -f deploy/k8s/hpa.yaml

  # Monitoring stack
  kubectl apply -f deploy/monitoring/prometheus.yaml
  kubectl apply -f deploy/monitoring/grafana.yaml

  log "Kubernetes resources applied"
fi

# ── 8. Nginx reverse proxy ────────────────────────────────────────
header "Nginx Configuration"
cat > /etc/nginx/sites-available/alchemy << NGXEOF
# Rate limiting
limit_req_zone \$binary_remote_addr zone=api:10m rate=20r/s;
limit_req_zone \$binary_remote_addr zone=auth:10m rate=5r/m;

server {
    listen 80;
    server_name $DOMAIN;

    # Auth endpoints — strict rate limit
    location /api/auth/login  { limit_req zone=auth burst=10 nodelay; proxy_pass http://127.0.0.1:8000; }
    location /api/auth/signup { limit_req zone=auth burst=5  nodelay; proxy_pass http://127.0.0.1:8000; }

    # WebSocket
    location /ws {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # API
    location /api/ {
        limit_req zone=api burst=50 nodelay;
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   Host \$host;
        proxy_read_timeout 60s;
    }

    # SPA + static
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   Host \$host;
    }

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;
}
NGXEOF

ln -sf /etc/nginx/sites-available/alchemy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
log "Nginx configured"

# ── 9. SSL Certificate ────────────────────────────────────────────
header "SSL Certificate (Let's Encrypt)"
if [[ "$DOMAIN" != *"nip.io"* ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    --email "$ADMIN_EMAIL" --redirect
  log "SSL certificate issued for $DOMAIN"
else
  warn "Using nip.io domain — skipping SSL (not supported for IP-based domains)"
fi

# Auto-renew SSL
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && systemctl reload nginx") | crontab -
log "SSL auto-renewal configured"

# ── 10. Systemd service (Docker) ──────────────────────────────────
if [[ "$ENABLE_K8S" != "true" ]]; then
  cat > /etc/systemd/system/alchemy.service << SVCEOF
[Unit]
Description=Alchemy Trading Platform
Requires=docker.service
After=docker.service

[Service]
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.production.yml up
ExecStop=/usr/bin/docker compose -f docker-compose.production.yml down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF
  systemctl daemon-reload
  systemctl enable alchemy
  log "Systemd service created"
fi

# ── 11. Update script ─────────────────────────────────────────────
cat > /usr/local/bin/alchemy-update << 'UPDEOF'
#!/bin/bash
set -e
APP_DIR=/opt/alchemy
echo "▶ Pulling latest code..."
cd $APP_DIR && git pull origin main
echo "▶ Rebuilding Docker image..."
docker build -t alchemy-app:latest .
echo "▶ Rolling restart (zero downtime)..."
docker compose -f docker-compose.production.yml up -d --no-deps --build app
echo "✓ Update complete"
UPDEOF
chmod +x /usr/local/bin/alchemy-update

# ── 12. Health check ─────────────────────────────────────────────
header "Health Check"
sleep 10
if curl -sf "http://localhost:8000/api/health" > /dev/null; then
  log "Application is running!"
else
  warn "Health check failed — check: docker compose -f $APP_DIR/docker-compose.production.yml logs"
fi

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  ✅  Alchemy Deployment Complete!${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}URL:${NC}          https://$DOMAIN"
echo -e "  ${BOLD}Admin email:${NC}  $ADMIN_EMAIL"
echo -e "  ${BOLD}Admin pass:${NC}   $ADMIN_PASS"
echo ""
echo -e "  ${BOLD}Commands:${NC}"
echo -e "    alchemy-update             # pull + redeploy"
echo -e "    docker compose -f $APP_DIR/docker-compose.production.yml logs -f"
if [[ "$ENABLE_K8S" == "true" ]]; then
echo -e "    kubectl get pods -n alchemy"
echo -e "    kubectl logs -n alchemy -l app=alchemy-app -f"
fi
echo ""
echo -e "  ${BOLD}⚠️  Save these secrets:${NC}"
echo -e "    JWT_SECRET_KEY = $JWT_SECRET"
echo -e "    VAULT_KEY      = $VAULT_KEY"
echo ""
echo -e "  ${BOLD}Configure email OTP:${NC}"
echo -e "    Edit $APP_DIR/.env.production"
echo -e "    Add: SMTP_USER=your@gmail.com"
echo -e "    Add: SMTP_PASSWORD=your_app_password"
echo -e "    Then: alchemy-update"
echo ""
