#!/bin/bash
# Alchemy SSL/HTTPS Setup — Run on VPS after DNS resolves
# Prerequisites: DNS A record for akilamirthya.in → 213.199.38.90
#
# Usage: ssh root@213.199.38.90 'bash -s' < deploy/setup-ssl.sh

set -e
DOMAIN="akilamirthya.in"
EMAIL="a.jaikumar.coimbatore@gmail.com"

echo "🔒 Alchemy SSL Setup — $(date)"
echo "Domain: $DOMAIN"

# Check DNS
echo "📡 Checking DNS..."
IP=$(dig +short $DOMAIN 2>/dev/null || echo "")
if [ -z "$IP" ]; then
    echo "⚠️  DNS not resolving yet. Set A record: $DOMAIN → 213.199.38.90"
    echo "   Then wait 5-30 min and retry."
    exit 1
fi
echo "✅ DNS resolves to $IP"

cd /opt/alchemy

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
    echo "📦 Installing certbot..."
    apt-get update -qq && apt-get install -y -qq certbot
fi

# Stop nginx temporarily for standalone verification
echo "🛑 Stopping nginx for cert verification..."
docker compose -f docker-compose.prod.yml stop nginx 2>/dev/null || true

# Get certificate
echo "📜 Requesting Let's Encrypt certificate..."
certbot certonly --standalone \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email \
    --non-interactive

# Copy certs
echo "📋 Copying certificates..."
mkdir -p /opt/alchemy/ssl
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/alchemy/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/alchemy/ssl/
chmod 600 /opt/alchemy/ssl/*.pem

# Update nginx config for HTTPS
echo "🔧 Updating nginx configuration..."
cat > /opt/alchemy/deploy/nginx-ssl.conf << 'NGINX'
server {
    listen 80;
    server_name akilamirthya.in www.akilamirthya.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name akilamirthya.in www.akilamirthya.in;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;

    # API proxy
    location /api/ {
        proxy_pass http://alchemy:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket proxy
    location /ws {
        proxy_pass http://alchemy:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Frontend static files
    location / {
        proxy_pass http://alchemy:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

# Restart services
echo "🚀 Restarting services with SSL..."
docker compose -f docker-compose.prod.yml up -d

# Setup auto-renewal
echo "🔄 Setting up cert auto-renewal..."
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/*.pem /opt/alchemy/ssl/ && docker compose -f /opt/alchemy/docker-compose.prod.yml restart nginx") | crontab -

echo ""
echo "✅ SSL setup complete!"
echo "   https://$DOMAIN"
echo "   Auto-renewal: daily at 3 AM"
