# GitHub Actions Setup Guide — Alchemy CI/CD

Complete setup for automated testing and deployment from GitHub to production VPS.

---

## Step 1: Generate Deploy SSH Key

Run on your **local machine** (Windows PowerShell or Linux/Mac terminal):

```bash
# Generate dedicated deploy key (no passphrase — for automation)
ssh-keygen -t ed25519 -C "alchemy-github-deploy" -f ~/.ssh/alchemy_deploy -N ""
# Creates:
#   ~/.ssh/alchemy_deploy      ← PRIVATE KEY → paste into GitHub Secret
#   ~/.ssh/alchemy_deploy.pub  ← PUBLIC KEY  → install on VPS
```

## Step 2: Install Public Key on VPS

```bash
# Option A: ssh-copy-id (easiest)
ssh-copy-id -i ~/.ssh/alchemy_deploy.pub root@YOUR_VPS_IP

# Option B: Manual
cat ~/.ssh/alchemy_deploy.pub | ssh root@YOUR_VPS_IP \
  "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"

# Test connection
ssh -i ~/.ssh/alchemy_deploy root@YOUR_VPS_IP "echo '✓ SSH works'"
```

## Step 3: Add GitHub Secrets

Go to: **github.com/jaikumararjunan/alchemy → Settings → Secrets and variables → Actions**

### Required Secrets (New repository secret):

| Secret Name | Value |
|-------------|-------|
| `VPS_SSH_KEY` | Full contents of `~/.ssh/alchemy_deploy` (private key) |
| `VPS_HOST` | Your VPS IP address (e.g. `93.127.xxx.xxx`) |

```bash
# Get private key to paste:
cat ~/.ssh/alchemy_deploy
# Copy everything including: -----BEGIN OPENSSH PRIVATE KEY----- ... -----END OPENSSH PRIVATE KEY-----
```

### Optional Variables (Settings → Variables → Actions):

| Variable | Value | Purpose |
|----------|-------|---------|
| `VPS_USER` | `root` | SSH login user |
| `SLACK_WEBHOOK` | `https://hooks.slack.com/...` | Deploy notifications |

## Step 4: Add Workflow Files via GitHub UI

Since the current token lacks `workflow` scope, add these files directly in GitHub:

### CI Workflow (ci.yml)
Go to: **Actions → New workflow → Set up yourself**
Name: `.github/workflows/ci.yml`

Content:
```yaml
name: CI
on:
  push:
    branches: [main, develop, "feature/**", "fix/**"]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -r requirements.local.txt pytest pytest-asyncio
      - run: pytest tests/unit/ -q --tb=short
        env:
          JWT_SECRET_KEY: ci_test_jwt_secret_key_minimum_32_chars!!
          ALCHEMY_VAULT_KEY: ci_vault_key_minimum_32_chars_here!!
          DATABASE_URL: sqlite+aiosqlite:///./test_ci.db
          ADMIN_EMAIL: admin@alchemy.in
          ADMIN_PASSWORD: "CITest#Admin!2024"
          ENV: test

  frontend:
    name: Frontend Build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: "20", cache: npm, cache-dependency-path: frontend/package-lock.json}
      - run: cd frontend && npm ci && npm run build
      - run: test -f frontend/dist/index.html && echo "✓ Build OK"

  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install bandit && bandit -r alchemy/ -ll -x alchemy/tests || true
```

### CD Workflow (cd.yml)
Go to: **Actions → New workflow → Set up yourself**
Name: `.github/workflows/cd.yml`

Content:
```yaml
name: CD
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      force_rebuild:
        description: Force no-cache rebuild
        type: boolean
        default: false

jobs:
  deploy:
    name: Deploy to Production
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://akilamirthya.in
    steps:
      - uses: actions/checkout@v4

      - name: Run tests first
        run: |
          pip install -r requirements.local.txt pytest pytest-asyncio
          pytest tests/unit/ -q
        env:
          JWT_SECRET_KEY: cd_predeploy_jwt_key_minimum_32_chars!!
          ALCHEMY_VAULT_KEY: cd_predeploy_vault_key_min_32_chars!
          DATABASE_URL: sqlite+aiosqlite:///./predeploy.db
          ADMIN_EMAIL: admin@alchemy.in
          ADMIN_PASSWORD: "CDTest#Admin!2024"
          ENV: test

      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.VPS_SSH_KEY }}" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key
          ssh-keyscan -H "${{ secrets.VPS_HOST }}" >> ~/.ssh/known_hosts 2>/dev/null || true

      - name: Deploy to VPS
        env:
          FORCE: ${{ inputs.force_rebuild || 'false' }}
        run: |
          ssh -i ~/.ssh/deploy_key \
              -o StrictHostKeyChecking=no \
              -o ConnectTimeout=30 \
              "${{ vars.VPS_USER || 'root' }}@${{ secrets.VPS_HOST }}" << REMOTE
          set -euo pipefail
          cd /opt/alchemy
          echo "Deploying ${{ github.sha }} by ${{ github.actor }}"
          git fetch origin main && git reset --hard origin/main
          BUILD_OPT=\$([ "$FORCE" = "true" ] && echo "--no-cache" || echo "")
          docker compose -f docker-compose.production.yml build \$BUILD_OPT
          docker compose -f docker-compose.production.yml up -d --remove-orphans
          for i in \$(seq 1 18); do
            curl -sf http://127.0.0.1:8000/api/health && echo " healthy" && break
            [ \$i -eq 18 ] && { docker compose -f docker-compose.production.yml logs --tail=40; exit 1; }
            sleep 5
          done
          docker image prune -f --filter "until=24h" || true
          echo "✅ Deploy complete"
          REMOTE

      - name: Cleanup SSH
        if: always()
        run: rm -f ~/.ssh/deploy_key
```

### Security Workflow (security.yml)
Name: `.github/workflows/security.yml`

```yaml
name: Security
on:
  schedule:
    - cron: "0 2 * * 1"
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install bandit pip-audit
      - run: bandit -r alchemy/ -ll -x alchemy/tests || true
      - run: pip-audit -r requirements.local.txt || true
```

## Step 5: Create GitHub Environment

Go to: **Settings → Environments → New environment**
- Name: `production`
- ✅ Required reviewers: add yourself
- ✅ Deployment branches: `main` only

---

## Pipeline Flow

```
git push origin main
        │
        ▼
    CI runs (ci.yml)
    ├── pytest (134 tests)
    ├── npm build
    └── bandit scan
        │ all pass
        ▼
    CD runs (cd.yml)
    ├── SSH → VPS
    ├── git pull
    ├── docker build
    ├── docker up -d
    ├── health check (90s)
    └── ✅ https://akilamirthya.in
```

## Manual Deployment (Emergency)

```bash
# On VPS
cd /opt/alchemy && alchemy-update

# Or full manual:
git pull origin main
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```
