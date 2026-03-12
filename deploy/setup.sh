#!/usr/bin/env bash
# =============================================================================
# Alchemy — Production Server Setup Script
# Run once on a fresh Ubuntu 22.04 LTS VPS.
#
# Usage:
#   chmod +x deploy/setup.sh
#   sudo ./deploy/setup.sh
#
# After this script:
#   1. Copy your .env to /opt/alchemy/.env
#   2. Run: cd /opt/alchemy && docker compose -f docker-compose.prod.yml up -d
# =============================================================================
set -euo pipefail

ALCHEMY_USER="alchemy"
ALCHEMY_DIR="/opt/alchemy"
REPO_URL="${REPO_URL:-https://github.com/jaikumararjunan/alchemy.git}"
DOMAIN="${DOMAIN:-akilamirthya.in}"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Require root ─────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "This script must be run as root."

info "=== Alchemy production setup starting ==="

# ── System update ─────────────────────────────────────────────────────────────
info "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git ufw fail2ban \
    ca-certificates gnupg lsb-release \
    htop ncdu jq unzip logrotate

# ── Docker ───────────────────────────────────────────────────────────────────
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
    info "Docker already installed: $(docker --version)"
fi

# ── Dedicated user ────────────────────────────────────────────────────────────
if ! id "$ALCHEMY_USER" &>/dev/null; then
    info "Creating user: $ALCHEMY_USER"
    useradd -r -m -d "$ALCHEMY_DIR" -s /bin/bash "$ALCHEMY_USER"
    usermod -aG docker "$ALCHEMY_USER"
else
    info "User $ALCHEMY_USER already exists"
    usermod -aG docker "$ALCHEMY_USER"
fi

# ── Application directory ─────────────────────────────────────────────────────
info "Setting up $ALCHEMY_DIR..."
mkdir -p "$ALCHEMY_DIR"/{ssl,logs,deploy}
chown -R "$ALCHEMY_USER:$ALCHEMY_USER" "$ALCHEMY_DIR"

# ── Firewall ──────────────────────────────────────────────────────────────────
info "Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

# ── Fail2ban ──────────────────────────────────────────────────────────────────
info "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port    = ssh

[nginx-http-auth]
enabled = true
EOF
systemctl enable --now fail2ban

# ── Kernel tweaks for WebSocket / high-throughput ────────────────────────────
info "Applying kernel network tuning..."
cat >> /etc/sysctl.conf <<'EOF'

# Alchemy network tuning
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.core.netdev_max_backlog = 65535
EOF
sysctl -p

# ── systemd service (wrapper around docker compose) ───────────────────────────
info "Installing alchemy systemd service..."
cat > /etc/systemd/system/alchemy.service <<EOF
[Unit]
Description=Alchemy AI Trading Bot (Docker Compose)
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$ALCHEMY_USER
WorkingDirectory=$ALCHEMY_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker compose -f docker-compose.prod.yml pull && \\
           /usr/bin/docker compose -f docker-compose.prod.yml up -d --remove-orphans
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable alchemy

# ── Log rotation ──────────────────────────────────────────────────────────────
info "Configuring log rotation..."
cat > /etc/logrotate.d/alchemy <<EOF
$ALCHEMY_DIR/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 $ALCHEMY_USER $ALCHEMY_USER
}
EOF

# ── Deploy script ─────────────────────────────────────────────────────────────
cat > "$ALCHEMY_DIR/deploy/deploy.sh" <<'DEPLOY'
#!/usr/bin/env bash
# Rolling deploy — pull new image and restart
set -euo pipefail

IMAGE_TAG="${1:-latest}"
DRY_RUN="${2:-false}"

cd /opt/alchemy

# Pull new image
docker compose -f docker-compose.prod.yml pull alchemy

# Update env
sed -i "s/^DRY_RUN=.*/DRY_RUN=${DRY_RUN}/" .env

# Rolling restart (zero-downtime via healthcheck)
docker compose -f docker-compose.prod.yml up -d --no-deps --remove-orphans alchemy

echo "Deploy complete. Image: ${IMAGE_TAG}, DRY_RUN=${DRY_RUN}"
DEPLOY
chmod +x "$ALCHEMY_DIR/deploy/deploy.sh"
chown "$ALCHEMY_USER:$ALCHEMY_USER" "$ALCHEMY_DIR/deploy/deploy.sh"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
info "=== Setup complete! ==="
echo ""
echo "  Next steps:"
echo "  1.  cp .env.example $ALCHEMY_DIR/.env"
echo "  2.  nano $ALCHEMY_DIR/.env           # add API keys"
echo "  3.  cp docker-compose.prod.yml $ALCHEMY_DIR/"
echo "  4.  cp -r deploy/ $ALCHEMY_DIR/deploy/"
echo "  5.  sudo systemctl start alchemy"
echo "  6.  sudo certbot --nginx -d $DOMAIN   # after DNS is pointed"
echo ""
