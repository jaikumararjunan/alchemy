#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE"

mkdir -p data

if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv
fi

if [[ ! -f .env.local ]]; then
  cat > .env.local <<EOF
ENV=development
DATABASE_URL=sqlite+aiosqlite:////${WORKSPACE}/data/alchemy.db
JWT_SECRET_KEY=AlchemyLocalDev!JWT_Secret_Key_32chars_Min_2024
ALCHEMY_VAULT_KEY=AlchemyLocalDev!Vault_Key_32chars_Min2024!!
ADMIN_EMAIL=admin@alchemy.in
ADMIN_PASSWORD=Alchemy#Admin!2024
EOF
fi

if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q -U pip
python -m pip install -r requirements.local.txt
python -m pip install pytest pytest-asyncio

cd frontend
npm ci --silent
npm run build
cd "$WORKSPACE"

echo "cloud-agent-install: ok"
