#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Alchemy Platform — Update Script
# Run: sudo bash /opt/alchemy/deploy/update.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
INSTALL_DIR="/opt/alchemy"
APP_USER="alchemy"
GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}[UPDATE]${NC} Pulling latest code..."
cd $INSTALL_DIR && sudo -u $APP_USER git pull origin main

echo -e "${BLUE}[UPDATE]${NC} Installing new Python deps..."
sudo -u $APP_USER .venv/bin/pip install -r requirements.txt -q

echo -e "${BLUE}[UPDATE]${NC} Building frontend..."
cd $INSTALL_DIR/frontend && sudo -u $APP_USER npm install --silent && sudo -u $APP_USER npm run build

echo -e "${BLUE}[UPDATE]${NC} Restarting service..."
systemctl restart alchemy-api

sleep 3
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
[[ "$HTTP" == "200" ]] && echo -e "${GREEN}[OK]${NC} Update complete — v$(curl -s http://localhost:8000/health | python3 -c 'import sys,json;print(json.load(sys.stdin).get("version","?"))')" || echo "Check: systemctl status alchemy-api"
