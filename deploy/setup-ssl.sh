#!/bin/bash
# Alchemy SSL Setup — Run on VPS
# Prerequisites: DNS A record pointing to 213.199.38.90

set -e
DOMAIN="akilamirthya.in"
EMAIL="a.jaikumar.coimbatore@gmail.com"

echo "=== Step 1: Create SSL directory ==="
mkdir -p /opt/alchemy/ssl

echo "=== Step 2: Get certificate via certbot ==="
cd /opt/alchemy
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email

echo "=== Step 3: Copy certs ==="
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/alchemy/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/alchemy/ssl/

echo "=== Step 4: Reload nginx ==="
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

echo "=== Step 5: Setup auto-renewal cron ==="
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/alchemy && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/*.pem /opt/alchemy/ssl/ && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload") | crontab -

echo "✅ SSL configured! Visit https://$DOMAIN"
