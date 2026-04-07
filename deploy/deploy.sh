#!/usr/bin/env bash
set -euo pipefail

IMAGE_REF="${1:-}"
DRY_RUN_VALUE="${2:-false}"
APP_DIR="/opt/alchemy"

if [[ -z "$IMAGE_REF" ]]; then
  echo "Usage: deploy.sh <image-ref> [dry-run]"
  exit 1
fi

cd "$APP_DIR"

if [[ ! -f "docker-compose.prod.yml" ]]; then
  echo "docker-compose.prod.yml not found in $APP_DIR"
  exit 1
fi

echo "Deploying image: $IMAGE_REF"
echo "DRY_RUN=$DRY_RUN_VALUE"

export IMAGE_REF
export DRY_RUN="$DRY_RUN_VALUE"

chmod +x "$APP_DIR/deploy/deploy.sh" || true

docker compose -f docker-compose.prod.yml pull alchemy || true
docker compose -f docker-compose.prod.yml up -d --remove-orphans

docker compose -f docker-compose.prod.yml ps
