#!/bin/bash
# Alchemy VPS Rebuild Script
# Usage: ssh root@213.199.38.90 'bash -s' < deploy/rebuild.sh

set -e
echo "🔮 Alchemy VPS Rebuild — $(date)"

cd /opt/alchemy || { echo "❌ /opt/alchemy not found"; exit 1; }

# Pull latest
echo "📥 Pulling latest code..."
git pull origin main

# Build
echo "🔨 Building Docker image..."
docker compose -f docker-compose.prod.yml build --no-cache alchemy

# Deploy
echo "🚀 Deploying..."
docker compose -f docker-compose.prod.yml up -d alchemy

# Health check
echo "⏳ Waiting for health check..."
sleep 5
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Health check passed (HTTP $HTTP_CODE)"
else
    echo "⚠️ Health check returned HTTP $HTTP_CODE"
    echo "Checking logs..."
    docker compose -f docker-compose.prod.yml logs --tail=20 alchemy
fi

echo ""
echo "=== Container Status ==="
docker compose -f docker-compose.prod.yml ps
echo ""
echo "=== Disk Usage ==="
df -h /data 2>/dev/null || df -h /
echo ""
echo "🔮 Rebuild complete — $(date)"
