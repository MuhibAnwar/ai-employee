#!/usr/bin/env bash
# cloud_setup.sh — One-time VM initialization for AI Employee (Platinum Tier)
# Target: Oracle Cloud Free Tier, Ubuntu 22.04 ARM
#
# Usage:
#   chmod +x deployment/cloud_setup.sh
#   ./deployment/cloud_setup.sh
#
# Run from the project root directory.

set -euo pipefail
IFS=$'\n\t'

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[setup]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
section() { echo -e "\n${GREEN}══════════════════════════════════════════${NC}"; \
             echo -e "${GREEN}  $*${NC}"; \
             echo -e "${GREEN}══════════════════════════════════════════${NC}"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
info "Project root: $PROJECT_ROOT"

# ── 1. System packages ───────────────────────────────────────────────────────
section "1/8 System packages"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    git curl wget unzip \
    python3 python3-pip python3-venv python3-dev \
    build-essential libssl-dev \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libasound2 libxshmfence1 \
    xvfb                           # virtual display for headed Playwright sessions
info "System packages installed"

# ── 2. Node.js 20 LTS ────────────────────────────────────────────────────────
section "2/8 Node.js 20"
if ! node --version 2>/dev/null | grep -q "^v20"; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
info "Node $(node --version), npm $(npm --version)"

# ── 3. PM2 (process manager) ─────────────────────────────────────────────────
section "3/8 PM2"
if ! command -v pm2 &>/dev/null; then
    sudo npm install -g pm2
fi
info "PM2 $(pm2 --version)"

# ── 4. Python virtual environment ────────────────────────────────────────────
section "4/8 Python venv + dependencies"
cd "$PROJECT_ROOT"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    info "Created .venv"
fi
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
info "Python dependencies installed"

# ── 5. Playwright Chromium ───────────────────────────────────────────────────
section "5/8 Playwright Chromium"
python -m playwright install chromium
info "Playwright Chromium installed"

# ── 6. Email MCP server (Node.js) ────────────────────────────────────────────
section "6/8 Email MCP npm install"
if [ -f "$PROJECT_ROOT/mcp-servers/email-mcp/package.json" ]; then
    cd "$PROJECT_ROOT/mcp-servers/email-mcp"
    npm install --quiet
    cd "$PROJECT_ROOT"
    info "Email MCP dependencies installed"
else
    warn "mcp-servers/email-mcp/package.json not found — skipping"
fi

# ── 7. Vault directory structure ─────────────────────────────────────────────
section "7/8 Vault directories"
VAULT="$PROJECT_ROOT/vault"
for dir in Inbox Needs_Action Plans Pending_Approval Approved Rejected Done Logs Accounting Briefings secrets; do
    mkdir -p "$VAULT/$dir"
done
# secrets should not be world-readable
chmod 700 "$PROJECT_ROOT/secrets" 2>/dev/null || true
info "Vault directories ready"

# ── 8. .env check ────────────────────────────────────────────────────────────
section "8/8 Environment file"
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    warn ".env created from .env.example — EDIT IT before starting watchers"
    warn "  nano $PROJECT_ROOT/.env"
else
    info ".env already exists"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env:                  nano $PROJECT_ROOT/.env"
echo "    2. Transfer secrets from local machine:"
echo "         scp -r ./secrets ubuntu@<VM_IP>:$PROJECT_ROOT/secrets"
echo "    3. Start watchers:             ./deployment/cloud_watchers.sh"
echo ""
