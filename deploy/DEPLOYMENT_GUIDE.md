# 🔮 Alchemy Trading Platform — Hostinger VPS Deployment Guide

## One-Click Deployment

```bash
# Set your domain first, then run:
DOMAIN=alchemy.yourdomain.com \
ADMIN_EMAIL=admin@yourdomain.com \
bash <(curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/install.sh)
```

That's it. The script handles everything: Python, Node.js, Nginx, SSL, systemd.

---

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| Plan | KVM2 (4 vCPU, 8 GB) | KVM4 (8 vCPU, 16 GB) |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Storage | 50 GB SSD | 100 GB NVMe |
| Bandwidth | 200 Mbps | 400 Mbps |

**Get a VPS:** https://www.hostinger.in/vps-hosting

---

## Step-by-Step Manual Deployment

### 1. Order Hostinger VPS

1. Go to hostinger.in → VPS Hosting → Select **KVM 2** or higher
2. Choose **Ubuntu 22.04 LTS**
3. Set a strong root password or SSH key
4. Note your VPS IP address

### 2. Point DNS

In your domain registrar (or Hostinger DNS):
```
A    alchemy.yourdomain.com    →  YOUR_VPS_IP
A    www.alchemy.yourdomain.com →  YOUR_VPS_IP
```
Wait 5-15 minutes for propagation.

### 3. SSH into your VPS

```bash
ssh root@YOUR_VPS_IP
# Or with SSH key:
ssh -i ~/.ssh/your_key root@YOUR_VPS_IP
```

### 4. Run One-Click Installer

```bash
# Option A: Pipe to bash (fastest)
DOMAIN=alchemy.yourdomain.com \
ADMIN_EMAIL=your@email.com \
bash <(curl -fsSL https://raw.githubusercontent.com/jaikumararjunan/alchemy/main/deploy/install.sh)

# Option B: Clone then run
git clone https://github.com/jaikumararjunan/alchemy.git /opt/alchemy
DOMAIN=alchemy.yourdomain.com bash /opt/alchemy/deploy/install.sh
```

### 5. First Login

After installation completes:
1. Open `https://alchemy.yourdomain.com`
2. Click **Sign In**
3. Email: `admin@alchemy.in` (or your ADMIN_EMAIL)
4. Password: shown at end of install script (also in `/opt/alchemy/.env`)

---

## What the Installer Configures

```
/opt/alchemy/                     ← Application root
├── .env                          ← Auto-generated secrets
├── .venv/                        ← Python 3.11 virtual env
├── static/                       ← Built React frontend
├── data/
│   ├── alchemy.db               ← SQLite database
│   ├── chromadb/                ← Vector DB for EI system
│   └── logs/api.log             ← Application logs
├── alchemy/                      ← Python backend
└── frontend/                     ← React source

/etc/systemd/system/
└── alchemy-api.service          ← Systemd service

/etc/nginx/sites-available/
└── alchemy                      ← Nginx config with SSL
```

---

## Post-Installation: Configure Exchange APIs

### Method 1: Via API (recommended)
```bash
# Get your access token first
TOKEN=$(curl -s -X POST https://alchemy.yourdomain.com/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@alchemy.in","password":"YOUR_PASSWORD"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Register Delta Exchange (paper mode for safety)
curl -X POST https://alchemy.yourdomain.com/tokens/register \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "exchange": "delta",
    "api_key": "YOUR_DELTA_API_KEY",
    "api_secret": "YOUR_DELTA_SECRET",
    "paper_mode": true,
    "testnet": true
  }'
```

### Method 2: Edit .env directly
```bash
nano /opt/alchemy/.env
# Add:
DELTA_API_KEY=your_key
DELTA_API_SECRET=your_secret
systemctl restart alchemy-api
```

---

## Notification Setup

### Telegram (Recommended)
```bash
curl -X POST https://alchemy.yourdomain.com/notifications/channels \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "My Telegram",
    "provider": "telegram",
    "config": {
      "bot_token": "YOUR_BOT_TOKEN",
      "chat_id": "YOUR_CHAT_ID"
    }
  }'
```

### Test notifications
```bash
curl -X POST https://alchemy.yourdomain.com/notifications/channels/CHANNEL_ID/test \
  -H "Authorization: Bearer $TOKEN"
```

---

## Upgrade to PostgreSQL (Production)

```bash
# 1. Configure PostgreSQL
sudo -u postgres psql -c "CREATE USER alchemy WITH PASSWORD 'strong_password';"
sudo -u postgres psql -c "CREATE DATABASE alchemy OWNER alchemy;"

# 2. Update .env
sed -i "s|DATABASE_URL=sqlite.*|DATABASE_URL=postgresql+asyncpg://alchemy:strong_password@localhost:5432/alchemy|" /opt/alchemy/.env

# 3. Run migration
/opt/alchemy/.venv/bin/python3 -c "
import asyncio
from alchemy.api.database import create_tables
asyncio.run(create_tables())
print('PostgreSQL tables created')
"

# 4. Restart
systemctl restart alchemy-api
```

---

## Monitoring & Maintenance

### Check service status
```bash
systemctl status alchemy-api
journalctl -u alchemy-api -f          # Live logs
tail -f /opt/alchemy/data/logs/api.log
```

### Update to latest version
```bash
sudo bash /opt/alchemy/deploy/update.sh
```

### Backup
```bash
# Daily backup script
cat > /etc/cron.daily/alchemy-backup << 'CRON'
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR=/var/backups/alchemy
mkdir -p $BACKUP_DIR
cp /opt/alchemy/data/alchemy.db $BACKUP_DIR/alchemy_$DATE.db
cp /opt/alchemy/.env $BACKUP_DIR/env_$DATE.bak
# Keep 30 days
find $BACKUP_DIR -mtime +30 -delete
CRON
chmod +x /etc/cron.daily/alchemy-backup
```

### SSL renewal (automatic via certbot)
```bash
certbot renew --dry-run     # Test
certbot renew               # Force renew
```

---

## Security Hardening (Post-Install)

```bash
# Change SSH port
sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config
ufw allow 2222/tcp && ufw delete allow ssh
systemctl restart sshd

# Disable root login
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# Enable automatic security updates
apt install unattended-upgrades -y
dpkg-reconfigure -f noninteractive unattended-upgrades

# Set up Fail2ban for API
cat > /etc/fail2ban/jail.d/alchemy.conf << 'F2B'
[alchemy-auth]
enabled = true
port = 80,443
filter = alchemy-auth
logpath = /opt/alchemy/data/logs/api.log
maxretry = 10
bantime = 3600
F2B
systemctl restart fail2ban
```

---

## Hostinger-Specific Tips

1. **Snapshot before deployment**: Take a Hostinger snapshot before running the installer
2. **Firewall**: Hostinger has a panel firewall — also enable UFW as defence-in-depth
3. **IPv6**: Add AAAA records if your VPS has IPv6
4. **Cloudflare** (optional): Put Cloudflare in front for DDoS protection + CDN
5. **Private networking**: Use Hostinger private networks if running Redis/DB on separate VPS

---

## Troubleshooting

| Issue | Command | Fix |
|-------|---------|-----|
| API not starting | `systemctl status alchemy-api` | Check `.env` file |
| 502 Bad Gateway | `curl localhost:8000/health` | Restart API service |
| SSL not working | `certbot certificates` | Run `certbot --nginx -d domain` |
| DB locked | `ls -la /opt/alchemy/data/` | Switch to PostgreSQL |
| Login fails | `curl -X POST localhost:8000/auth/login -d '...'` | Check DB tables |

### Reset admin password
```bash
/opt/alchemy/.venv/bin/python3 << 'EOF'
import asyncio, os
os.chdir('/opt/alchemy')
# Load env
for line in open('.env').readlines():
    if '=' in line and not line.startswith('#'):
        k,v = line.strip().split('=',1)
        os.environ.setdefault(k,v)

async def reset():
    from alchemy.api.database import get_session_factory
    from alchemy.auth.service import AuthService
    from sqlalchemy import select
    from alchemy.users.models import User
    async with get_session_factory()() as db:
        result = await db.execute(select(User).where(User.email=="admin@alchemy.in"))
        user = result.scalar_one_or_none()
        if user:
            from alchemy.auth.security import hash_password
            user.password_hash = hash_password("NewAlchemy#Admin!2024")
            await db.commit()
            print("Password reset to: NewAlchemy#Admin!2024")

asyncio.run(reset())
EOF
```
