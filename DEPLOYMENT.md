# Alchemy Trading Platform — Deployment Guide

**Version:** 0.7.0 | **Codename:** Meridian | **Date:** 2026-04-05

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Hostinger VPS — Production](#hostinger-vps--production)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Notification Setup](#notification-setup)
7. [Security Checklist](#security-checklist)
8. [Maintenance & Updates](#maintenance--updates)
9. [Monitoring](#monitoring)
10. [Rollback Procedure](#rollback-procedure)

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.12.0 | 3.12.9 |
| Node.js | 18.0 | 20.x LTS |
| RAM | 2 GB | 8 GB |
| Storage | 20 GB | 100 GB NVMe |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Docker | 24.0 | 29.x |

---

## Local Development

```powershell
# Windows (PowerShell)
git clone https://github.com/jaikumararjunan/alchemy.git
cd alchemy

py -3.12 -m venv .venv
.venv\Scripts\activate

pip install -r requirements.local.txt
cd frontend && npm install && npm run build && cd ..

# Copy and configure environment
copy .env.example .env.local
# Edit .env.local with your settings

uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Open: http://localhost:8000
Login: `admin@alchemy.in` / `Alchemy#Admin!2024`

```bash
# Linux/Mac
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.local.txt
cd frontend && npm install && npm run build && cd ..
cp .env.example .env.local
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## Hostinger VPS — Production

### Step 1: Order VPS

| Setting | Value |
|---------|-------|
| Plan | KVM 2 (2 vCPU, 8 GB RAM minimum) |
| OS | Ubuntu 22.04 LTS |
| Location | Singapore (lowest latency for India) |
| Hostname | alchemy-prod |

### Step 2: Configure DNS

Add an A record pointing to your VPS IP:
```
Type: A
Name: alchemy  (or @ for root domain)
Value: YOUR_VPS_IP
TTL: 300
```

Wait 5–15 minutes for propagation before running the installer.

### Step 3: Run Installer

SSH into your VPS as root, then:

```bash
# Download installer with GitHub token (private repo)
curl -fsSL \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  "https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/install.sh" \
  -o install.sh

# Run with your configuration
DOMAIN=akilamirthya.in \
ADMIN_EMAIL=your@email.com \
ADMIN_PASS="YourStrong#Pass2024!" \
GH_TOKEN=YOUR_GITHUB_TOKEN \
bash install.sh
```

The installer takes 10–15 minutes and:
1. Updates system packages + installs security tools
2. Configures UFW firewall (SSH/80/443 only)
3. Sets up Fail2ban (bans IPs after 5 failed SSH attempts)
4. Installs Docker + docker-compose
5. Clones the repository to `/opt/alchemy`
6. Auto-generates JWT_SECRET and VAULT_KEY
7. Builds Docker image (3–5 min)
8. Configures Nginx with rate limiting
9. Issues Let's Encrypt SSL certificate
10. Creates systemd service (auto-start on reboot)

### Step 4: Install alchemy-update Command

```bash
cat > /usr/local/bin/alchemy-update << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/alchemy
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔮 Alchemy — Zero-Downtime Update"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd $APP_DIR
echo "▶ Pulling latest code..."
git pull origin main
echo "▶ Rebuilding Docker image..."
docker compose -f docker-compose.production.yml build
echo "▶ Restarting container..."
docker compose -f docker-compose.production.yml up -d
echo "▶ Waiting for health check..."
sleep 15
curl -sf http://127.0.0.1:8000/api/health && echo "✅ Healthy" || echo "❌ Unhealthy"
docker compose -f docker-compose.production.yml ps
EOF
chmod +x /usr/local/bin/alchemy-update
```

### Step 5: Configure Email OTP

```bash
nano /opt/alchemy/.env.production
```

Add:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=abcdefghijklmnop    # 16-char App Password
SMTP_FROM=your@gmail.com
```

Then: `alchemy-update`

---

## Kubernetes Deployment

### Requirements
- Hostinger VPS Premium (4+ vCPU, 16+ GB RAM)
- Or any cloud K8s (GKE, EKS, AKS, DigitalOcean)

### Deploy with k3s (Lightweight K8s)

```bash
# Install with Kubernetes enabled
DOMAIN=akilamirthya.in \
ENABLE_K8S=true \
ADMIN_EMAIL=your@email.com \
GH_TOKEN=YOUR_TOKEN \
bash install.sh
```

### Apply Manifests Manually

```bash
# 1. Create namespace + secrets
kubectl apply -f deploy/k8s/namespace.yaml

kubectl create secret generic alchemy-secrets \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -base64 40)" \
  --from-literal=ALCHEMY_VAULT_KEY="$(openssl rand -base64 40)" \
  --from-literal=ADMIN_PASSWORD="YourStrong#Pass2024!" \
  --from-literal=SMTP_USER="your@gmail.com" \
  --from-literal=SMTP_PASSWORD="apppassword" \
  -n alchemy

# 2. Storage + Deployment
kubectl apply -f deploy/k8s/pvc.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/hpa.yaml

# 3. Monitoring
kubectl apply -f deploy/monitoring/prometheus.yaml
kubectl apply -f deploy/monitoring/grafana.yaml
kubectl apply -f deploy/monitoring/alertmanager.yaml

# 4. Check status
kubectl get pods -n alchemy
kubectl logs -n alchemy -l app=alchemy-app -f
```

### HPA Behavior
- Min: 2 pods (always-on HA)
- Max: 10 pods
- Scale up when: CPU > 70% OR memory > 80%
- Scale down: after 300 seconds stable

---

## Environment Variables Reference

### Required (All Environments)

| Variable | Example | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `40+ char random string with !@#` | JWT signing key — **never change after deploy** |
| `ALCHEMY_VAULT_KEY` | `40+ char random string with !@#` | AES-256 encryption key for exchange credentials |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/alchemy.db` | SQLite (dev/prod) or PostgreSQL URL |
| `ADMIN_EMAIL` | `admin@alchemy.in` | Initial super admin email |
| `ADMIN_PASSWORD` | `YourStrong#Pass2024!` | Must have uppercase+lowercase+digit+special |
| `ENV` | `production` | Controls auto-activation, log level, etc. |

### Optional (Notifications)

| Variable | Example | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (587=TLS, 465=SSL) |
| `SMTP_USER` | `you@gmail.com` | Gmail address |
| `SMTP_PASSWORD` | `abcdefghijklmnop` | Gmail 16-char App Password |
| `SMTP_FROM` | `you@gmail.com` | From address in emails |

### Optional (Configuration)

| Variable | Default | Description |
|----------|---------|-------------|
| `DOMAIN` | `localhost` | Production domain (used in notification links) |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `DB_ECHO` | `false` | Log all SQL queries (debug only) |
| `ENABLE_AI_AGENTS` | `false` | Enable LangGraph AI agent endpoints |

---

## Notification Setup

See **[SETUP_NOTIFICATIONS.md](./SETUP_NOTIFICATIONS.md)** for complete guides.

### Quick Reference

**Gmail:**
1. myaccount.google.com → Security → 2-Step Verification → App Passwords → Mail → Generate
2. Add to `.env.production`: `SMTP_USER=you@gmail.com` `SMTP_PASSWORD=xxxxxxxxxxxx`

**Telegram:**
1. @BotFather → /newbot → copy token
2. @userinfobot → copy Chat ID
3. Alchemy → Notifications → + Add Channel → Telegram

**WhatsApp (Twilio):**
1. twilio.com → get Account SID + Auth Token
2. Enable WhatsApp sandbox → join from your phone
3. Alchemy → Notifications → + Add Channel → WhatsApp

---

## Security Checklist

Run before every production deployment:

### Infrastructure
- [ ] UFW firewall active: `ufw status` → only 22/80/443 allowed
- [ ] Fail2ban running: `systemctl status fail2ban`
- [ ] SSL certificate valid: `certbot certificates`
- [ ] Docker not exposed: `netstat -tlnp | grep 8000` → should show `127.0.0.1` only

### Application
- [ ] `ENV=production` in `.env.production`
- [ ] `JWT_SECRET_KEY` is 40+ chars with special characters
- [ ] `ALCHEMY_VAULT_KEY` is 40+ chars with special characters
- [ ] Default admin password changed from `Alchemy#Admin!2024`
- [ ] SMTP configured (email OTP works)
- [ ] Admin account has 2FA enabled

### Access Control
- [ ] No other users have `super_admin` role (Admin Panel → Users → verify)
- [ ] All traders have 2FA enabled for live trading
- [ ] Rate limits active: `curl -X POST https://domain/api/auth/login` 10+ times → 429

### Monitoring
- [ ] `/api/health` returns `{"status":"ok"}`
- [ ] `/metrics` returns Prometheus metrics
- [ ] Docker container healthy: `docker ps` → `(healthy)`
- [ ] Logs clean: `docker logs alchemy-app-1 2>&1 | grep ERROR | tail -5`

---

## Maintenance & Updates

### Zero-Downtime Update

```bash
# On the VPS
alchemy-update

# Or manually:
cd /opt/alchemy
git pull origin main
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

### Useful Commands

```bash
# View live logs
docker compose -f /opt/alchemy/docker-compose.production.yml logs -f

# Check container status
docker ps

# Restart service
systemctl restart alchemy

# Backup database
cp /var/lib/alchemy/alchemy.db /backup/alchemy-$(date +%Y%m%d-%H%M%S).db

# SSL renewal (runs automatically)
certbot renew --dry-run

# Check disk space
df -h

# Check memory
free -h
```

---

## Monitoring

### Prometheus Metrics

Available at `https://akilamirthya.in/metrics` (admin auth required in production)

| Metric | Type | Description |
|--------|------|-------------|
| `alchemy_uptime_seconds` | Gauge | Seconds since startup |
| `alchemy_requests_total` | Counter | Requests by method/path/status |
| `alchemy_request_duration_seconds` | Gauge | P50/P95 latency |
| `alchemy_errors_total` | Counter | Total 5xx errors |
| `alchemy_active_websockets` | Gauge | Live WS connections |

### Alert Rules

| Alert | Condition | Action |
|-------|-----------|--------|
| AlchemyDown | App unreachable for 1 min | Telegram alert immediately |
| HighCPU | CPU > 80% for 5 min | Telegram + HPA scales pods |
| HighMemory | Memory > 85% for 5 min | Telegram + investigate |
| HighErrorRate | 5xx > 5% for 2 min | Telegram + check logs |
| SlowResponses | P95 > 2s for 5 min | Telegram + performance review |

---

## Rollback Procedure

```bash
# See recent deployments
cd /opt/alchemy && git log --oneline -10

# Rollback to specific commit
git checkout COMMIT_HASH
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Or rollback to previous tag
git checkout v0.6.0
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Return to latest after investigation
git checkout main && git pull
alchemy-update
```

---

*Alchemy Trading Platform v0.7.0 | github.com/jaikumararjunan/alchemy*
