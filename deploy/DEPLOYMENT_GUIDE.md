# Alchemy AI Trading Platform — Contabo VPS Deployment Guide

**VPS:** Contabo 213.199.38.90  
**Domain:** akilamirthya.in (Hostinger DNS)  
**Stack:** Docker Compose → Nginx + FastAPI + React + SQLite  
**Commits:** 205 | **Routes:** 303 | **Tests:** 403 pass

---

## Prerequisites

| Item | Status | Notes |
|------|--------|-------|
| Contabo VPS access | ✅ | SSH root@213.199.38.90 |
| Domain DNS | ⚠️ Check | A record: akilamirthya.in → 213.199.38.90 |
| Docker installed | ✅ | docker + docker compose |
| Git installed | ✅ | Git 2.x |
| GitHub PAT | ✅ | `YOUR_GITHUB_PAT` |

---

## Step 1: SSH into VPS

```bash
ssh root@213.199.38.90
```

---

## Step 2: Clone or Update Repository

### First Time Setup (if /opt/alchemy doesn't exist):

```bash
# Clone repo
cd /opt
git clone https://YOUR_GITHUB_PAT@github.com/jaikumararjunan/alchemy.git
cd alchemy

# Create data directory
mkdir -p /data /var/lib/alchemy
chmod 777 /data /var/lib/alchemy
```

### If Already Cloned (update to latest):

```bash
cd /opt/alchemy
git pull origin main
```

---

## Step 3: Configure Environment Variables

```bash
# Create .env file from template
cp .env.example .env

# Generate secrets
JWT_SECRET=$(openssl rand -hex 32)
VAULT_KEY=$(openssl rand -hex 32)
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "generate-later")

# Edit .env with your values
cat > /opt/alchemy/.env << 'ENVEOF'
# ── Application ──
ENV=production
LOG_LEVEL=info
ENABLE_AI_AGENTS=true

# ── Security (CHANGE THESE) ──
JWT_SECRET_KEY=PASTE_YOUR_JWT_SECRET_HERE
ALCHEMY_VAULT_KEY=PASTE_YOUR_VAULT_KEY_HERE
ALCHEMY_FERNET_KEY=PASTE_YOUR_FERNET_KEY_HERE

# ── Database ──
DATABASE_URL=sqlite+aiosqlite:////data/alchemy.db

# ── Admin Bootstrap ──
ADMIN_EMAIL=admin@akilamirthya.in
ADMIN_PASSWORD=YourStrongAdminPassword123!

# ── Delta Exchange (optional — testnet) ──
DELTA_API_KEY=
DELTA_API_SECRET=
DELTA_TESTNET=true

# ── Telegram Bot (optional) ──
TELEGRAM_BOT_TOKEN=

# ── Rate Limiting ──
CREDENTIAL_STUFFING_LIMIT=20
ENVEOF

# Now paste your generated secrets:
sed -i "s/PASTE_YOUR_JWT_SECRET_HERE/$JWT_SECRET/" .env
sed -i "s/PASTE_YOUR_VAULT_KEY_HERE/$VAULT_KEY/" .env

echo "✅ .env configured"
echo "⚠️  Edit .env to add FERNET_KEY, DELTA keys, TELEGRAM token"
```

---

## Step 4: Build and Deploy

```bash
cd /opt/alchemy

# Build Docker image (includes frontend build)
docker compose -f docker-compose.prod.yml build --no-cache alchemy

# Start services
docker compose -f docker-compose.prod.yml up -d

# Verify
docker compose -f docker-compose.prod.yml ps
```

Expected output:
```
NAME       IMAGE           STATUS                    PORTS
alchemy    alchemy:latest  Up 30 seconds (healthy)   8000/tcp
nginx      nginx:alpine    Up 30 seconds             0.0.0.0:80->80/tcp
```

---

## Step 5: Verify Health

```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Expected:
# {
#     "status": "ok",
#     "version": "0.6.0",
#     "routes": 303
# }

# Check from outside (browser):
# http://213.199.38.90
# http://akilamirthya.in (if DNS resolves)
```

---

## Step 6: SSL/HTTPS Setup

### 6a. Verify DNS First

```bash
# Check if domain points to VPS
dig +short akilamirthya.in

# Should return: 213.199.38.90
# If not, go to Hostinger DNS panel:
#   Type: A, Name: @, Value: 213.199.38.90, TTL: 3600
#   Type: A, Name: www, Value: 213.199.38.90, TTL: 3600
# Wait 5-30 minutes for propagation
```

### 6b. Run SSL Setup

```bash
cd /opt/alchemy
bash deploy/setup-ssl.sh
```

This will:
1. Check DNS resolution
2. Install certbot if needed
3. Get Let's Encrypt certificate
4. Configure nginx for HTTPS
5. Set up auto-renewal cron (daily 3 AM)

After success:
```
https://akilamirthya.in  ← Your trading platform!
```

---

## Step 7: Create Admin Account

```bash
# The first signup becomes admin, or use the bootstrap:
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your@email.com",
    "password": "YourStrongPassword123!",
    "username": "jai",
    "full_name": "Jai Kumar"
  }'
```

---

## Step 8: Optional — Configure Telegram Bot

```bash
# 1. Message @BotFather on Telegram
#    Send: /newbot
#    Choose name: Alchemy Trading Bot
#    Get token: 1234567890:ABCdefGHIjklMNOpqrSTUVwxyz

# 2. Add token to .env
echo "TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUVwxyz" >> /opt/alchemy/.env

# 3. Restart
docker compose -f docker-compose.prod.yml restart alchemy

# 4. Message your bot /start on Telegram
# 5. Register via API:
curl -X POST http://localhost:8000/api/telegram/register \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "YOUR_CHAT_ID"}'
```

---

## Step 9: Optional — Delta Exchange Testnet

```bash
# 1. Create testnet account: https://testnet.delta.exchange
# 2. Generate API keys in testnet dashboard
# 3. Add to .env:
cat >> /opt/alchemy/.env << 'EOF'
DELTA_API_KEY=your_testnet_key
DELTA_API_SECRET=your_testnet_secret
DELTA_TESTNET=true
EOF

# 4. Restart
docker compose -f docker-compose.prod.yml restart alchemy

# 5. Verify:
curl -s http://localhost:8000/api/delta/status \
  -H "Authorization: Bearer YOUR_TOKEN" | python3 -m json.tool
```

---

## Daily Operations

### View Logs

```bash
# All logs
docker compose -f docker-compose.prod.yml logs -f alchemy

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 alchemy

# Filter errors
docker compose -f docker-compose.prod.yml logs alchemy 2>&1 | grep -i error
```

### Update to Latest Code

```bash
cd /opt/alchemy
bash deploy/rebuild.sh

# Or manually:
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache alchemy
docker compose -f docker-compose.prod.yml up -d alchemy
```

### Restart Services

```bash
# Restart app only
docker compose -f docker-compose.prod.yml restart alchemy

# Restart everything
docker compose -f docker-compose.prod.yml restart

# Full stop + start
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

### Database Backup

```bash
# SQLite backup
cp /data/alchemy.db /data/backups/alchemy_$(date +%Y%m%d_%H%M).db

# Auto backup cron (add this):
(crontab -l; echo "0 2 * * * cp /data/alchemy.db /data/backups/alchemy_\$(date +\%Y\%m\%d).db") | crontab -
mkdir -p /data/backups
```

### Monitor Disk Usage

```bash
df -h /
du -sh /data/alchemy.db
docker system df
```

### Clean Docker Cache

```bash
# Remove old images
docker image prune -f

# Full cleanup (careful!)
docker system prune -f
```

---

## Troubleshooting

### App Won't Start

```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# Check logs
docker compose -f docker-compose.prod.yml logs --tail=50 alchemy

# Common fixes:
# 1. Missing .env → cp .env.example .env and edit
# 2. Port conflict → lsof -i :8000
# 3. Permission issue → chmod 777 /data
# 4. Build failed → docker compose build --no-cache alchemy
```

### 502 Bad Gateway

```bash
# Nginx can't reach alchemy container
docker compose -f docker-compose.prod.yml restart alchemy
sleep 10
curl -s http://localhost:8000/health
```

### Database Locked

```bash
# SQLite locking issue (too many concurrent writes)
# Option A: Restart
docker compose -f docker-compose.prod.yml restart alchemy

# Option B: Migrate to PostgreSQL (recommended for production)
# Install postgres:
apt install postgresql postgresql-contrib
sudo -u postgres createuser alchemy --password
sudo -u postgres createdb alchemy_prod --owner=alchemy

# Run migration:
python3 scripts/migrate_to_postgres.py \
  --sqlite /data/alchemy.db \
  --postgres postgresql://alchemy:yourpass@localhost:5432/alchemy_prod

# Update .env:
# DATABASE_URL=postgresql+asyncpg://alchemy:yourpass@localhost:5432/alchemy_prod
```

### SSL Certificate Renewal Failed

```bash
# Manual renewal
certbot renew --force-renewal
cp /etc/letsencrypt/live/akilamirthya.in/*.pem /opt/alchemy/ssl/
docker compose -f docker-compose.prod.yml restart nginx
```

---

## Quick Reference Card

```
SSH:      ssh root@213.199.38.90
App:      http://213.199.38.90 (or https://akilamirthya.in after SSL)
API:      http://213.199.38.90/api/health
Logs:     docker compose -f docker-compose.prod.yml logs -f alchemy
Restart:  docker compose -f docker-compose.prod.yml restart alchemy
Update:   cd /opt/alchemy && bash deploy/rebuild.sh
Backup:   cp /data/alchemy.db /data/backups/alchemy_$(date +%Y%m%d).db
```

---

## Architecture on VPS

```
                    ┌─────────────────┐
     Port 80/443   │     Nginx       │  Reverse proxy + SSL
                    │  (Docker)       │  Rate limiting
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
     Port 8000     │    Alchemy      │  FastAPI + React (built-in)
     (internal)    │   (Docker)      │  303 API routes
                    │                 │  WebSocket price stream
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  /data/         │  SQLite database
                    │  alchemy.db     │  Paper trading state
                    │                 │  Audit logs
                    └─────────────────┘
```

---

*Alchemy AI Trading Platform — Contabo VPS Deployment Guide*
*VPS: 213.199.38.90 | Domain: akilamirthya.in | 205 commits*
