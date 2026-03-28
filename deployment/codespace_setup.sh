#!/usr/bin/env bash
# codespace_setup.sh — One-time setup + watcher launch for GitHub Codespace (Platinum Tier)
#
# This replaces cloud_setup.sh for Codespace environments.
# Key differences from Oracle VM:
#   - Node.js v24 already present (skip install)
#   - Ubuntu 24.04 x86_64 (not 22.04 ARM)
#   - User is "codespace", not "ubuntu"
#   - No DISPLAY needed — API-based watchers, Playwright runs headless
#   - PM2 startup hook scoped to codespace user (no reboot concerns)
#   - WhatsApp is local-only — NOT started here (not in orchestrator either)
#
# Usage:
#   chmod +x deployment/codespace_setup.sh
#   ./deployment/codespace_setup.sh           # full setup + start
#   ./deployment/codespace_setup.sh stop      # stop all PM2 processes
#   ./deployment/codespace_setup.sh restart   # restart orchestrator
#   ./deployment/codespace_setup.sh logs      # tail live logs
#   ./deployment/codespace_setup.sh status    # PM2 process table

set -euo pipefail
IFS=$'\n\t'

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[codespace]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}     $*"; }
section() { echo -e "\n${CYAN}══════════════════════════════════════════${NC}"; \
            echo -e "${CYAN}  $*${NC}"; \
            echo -e "${CYAN}══════════════════════════════════════════${NC}"; }
die()     { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP_NAME="ai-employee-orchestrator"
ECOSYSTEM="$PROJECT_ROOT/deployment/ecosystem.config.cjs"
COMMAND="${1:-setup}"

info "Project root: $PROJECT_ROOT"
info "Command: $COMMAND"

# ── Short-circuit commands (no setup needed) ─────────────────────────────────
case "$COMMAND" in
  stop)
    command -v pm2 &>/dev/null || die "PM2 not found. Run setup first."
    info "Stopping $APP_NAME..."
    pm2 stop "$APP_NAME" 2>/dev/null || warn "Process not running"
    pm2 delete "$APP_NAME" 2>/dev/null || true
    pm2 save
    info "Stopped."
    exit 0
    ;;
  logs)
    command -v pm2 &>/dev/null || die "PM2 not found. Run setup first."
    exec pm2 logs "$APP_NAME" --lines 200
    ;;
  status)
    command -v pm2 &>/dev/null || die "PM2 not found. Run setup first."
    pm2 status
    exit 0
    ;;
  restart)
    command -v pm2 &>/dev/null || die "PM2 not found. Run setup first."
    pm2 restart "$APP_NAME"
    pm2 status
    exit 0
    ;;
  setup|start)
    : # fall through to setup steps
    ;;
  *)
    die "Unknown command: $COMMAND\nUsage: codespace_setup.sh [setup|start|stop|restart|logs|status]"
    ;;
esac

# ═════════════════════════════════════════════════════════════════════════════
# SETUP STEPS
# ═════════════════════════════════════════════════════════════════════════════

# ── 1. Verify Node.js ────────────────────────────────────────────────────────
section "1/7  Node.js check"
if ! command -v node &>/dev/null; then
    die "Node.js not found. Codespace should have it pre-installed. Check devcontainer config."
fi
NODE_VER=$(node --version)
info "Node $NODE_VER — OK (no install needed, Codespace provides it)"

# ── 2. PM2 ───────────────────────────────────────────────────────────────────
section "2/7  PM2 (process manager)"
if ! command -v pm2 &>/dev/null; then
    info "Installing PM2 globally..."
    sudo npm install -g pm2
else
    info "PM2 $(pm2 --version) — already installed"
fi

# ── 3. Python virtual environment ────────────────────────────────────────────
section "3/7  Python venv + dependencies"
cd "$PROJECT_ROOT"
if [ ! -d ".venv" ]; then
    info "Creating .venv with $(python3 --version)..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
info "Python dependencies installed → .venv/bin/python"

# ── 4. Playwright Chromium (headless — for execute-approved posting) ──────────
section "4/7  Playwright Chromium (headless)"
# Watchers use API libraries (no browser), but /execute-approved uses Playwright
# Codespace is headless Linux — no DISPLAY or Xvfb needed for headless Chromium
if python -m playwright install --help &>/dev/null 2>&1; then
    python -m playwright install chromium 2>/dev/null && \
        info "Playwright Chromium installed" || \
        warn "Playwright Chromium install failed — social posting actions may not work"
else
    warn "Playwright not in requirements — skipping Chromium install"
fi

# ── 5. Email MCP server (Node.js) ────────────────────────────────────────────
section "5/7  Email MCP server"
MCP_PKG="$PROJECT_ROOT/mcp-servers/email-mcp/package.json"
if [ -f "$MCP_PKG" ]; then
    cd "$PROJECT_ROOT/mcp-servers/email-mcp"
    npm install --quiet
    cd "$PROJECT_ROOT"
    info "Email MCP npm dependencies installed"
else
    warn "mcp-servers/email-mcp/package.json not found — skipping"
fi

# ── 6. Vault directories ─────────────────────────────────────────────────────
section "6/7  Vault directories"
VAULT="$PROJECT_ROOT/vault"
for dir in Inbox Needs_Action Plans Pending_Approval Approved Rejected Done Logs Accounting Briefings; do
    mkdir -p "$VAULT/$dir"
done
mkdir -p "$PROJECT_ROOT/secrets"
chmod 700 "$PROJECT_ROOT/secrets"
info "Vault directories ready"

# ── 7. .env check ────────────────────────────────────────────────────────────
section "7/7  Environment file"
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    warn ".env created from .env.example"
    warn "Edit it before watchers will connect to real services:"
    warn "  nano $PROJECT_ROOT/.env"
else
    info ".env exists"
    # Show which keys are filled vs blank (without printing values)
    FILLED=$(grep -v '^#' "$PROJECT_ROOT/.env" | grep -v '^$' | grep '=.' | wc -l || true)
    BLANK=$(grep -v '^#'  "$PROJECT_ROOT/.env" | grep -v '^$' | grep '=$' | wc -l || true)
    info "  $FILLED keys configured, $BLANK keys empty"
fi

# ═════════════════════════════════════════════════════════════════════════════
# START ORCHESTRATOR VIA PM2
# Cloud watchers started: Gmail, LinkedIn, Facebook, Instagram, Twitter
# FileSystemWatcher also runs (monitors vault/Inbox/)
# WhatsApp: LOCAL ONLY — not started here (not in orchestrator)
# ═════════════════════════════════════════════════════════════════════════════
section "Starting AI Employee Orchestrator via PM2"

# Resolve VAULT_PATH from .env (default ./vault)
VAULT_PATH=$(grep -E '^VAULT_PATH=' "$PROJECT_ROOT/.env" 2>/dev/null \
             | cut -d= -f2 | tr -d '"' | tr -d "'" || echo "./vault")
[ -z "$VAULT_PATH" ] && VAULT_PATH="./vault"
info "Vault path: $VAULT_PATH"

# Generate PM2 ecosystem config for Codespace
cat > "$ECOSYSTEM" <<EOF
// PM2 Ecosystem Config — AI Employee Codespace (Platinum Tier)
// Auto-generated by codespace_setup.sh — do not edit manually
// Re-run ./deployment/codespace_setup.sh to regenerate.
//
// Cloud watchers active: Gmail, LinkedIn, Facebook, Instagram, Twitter, FileSystem
// WhatsApp is LOCAL ONLY — not managed here.

module.exports = {
  apps: [
    {
      name: "$APP_NAME",
      script: "$VENV_PYTHON",
      args: "scheduler/orchestrator.py --vault $VAULT_PATH",
      cwd: "$PROJECT_ROOT",
      interpreter: "none",
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: "30s",
      exp_backoff_restart_delay: 100,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        VAULT_PATH: "$VAULT_PATH",
        // No DISPLAY needed — API-based watchers, Playwright runs headless
      },
      env_file: "$PROJECT_ROOT/.env",
      log_date_format: "YYYY-MM-DDTHH:mm:ssZ",
      out_file: "$PROJECT_ROOT/vault/Logs/pm2-out.log",
      error_file: "$PROJECT_ROOT/vault/Logs/pm2-err.log",
      merge_logs: true,
    }
  ]
};
EOF
info "PM2 ecosystem config written → $ECOSYSTEM"

# Start or reload
if pm2 describe "$APP_NAME" &>/dev/null; then
    info "Reloading existing PM2 process..."
    pm2 reload "$ECOSYSTEM" --update-env
else
    info "Starting orchestrator for the first time..."
    pm2 start "$ECOSYSTEM"
fi

pm2 save
info "PM2 config saved (persists across Codespace restarts)"

# ── Verify ───────────────────────────────────────────────────────────────────
section "Verification"
sleep 3  # let orchestrator initialize
pm2 status

echo ""
info "PM2 log paths:"
echo "  stdout → $PROJECT_ROOT/vault/Logs/pm2-out.log"
echo "  stderr → $PROJECT_ROOT/vault/Logs/pm2-err.log"
echo ""
info "Useful commands:"
echo "  ./deployment/codespace_setup.sh status   # PM2 process table"
echo "  ./deployment/codespace_setup.sh logs     # live log stream"
echo "  ./deployment/codespace_setup.sh restart  # restart orchestrator"
echo "  ./deployment/codespace_setup.sh stop     # stop all"
echo "  pm2 monit                                 # interactive dashboard"
echo ""
info "Platinum Tier active — Codespace is now your 24/7 cloud agent."
echo ""
echo "  Cloud owns:  Email triage, social post drafts → vault/Pending_Approval/"
echo "  Local owns:  Approvals, WhatsApp, final send via MCP"
echo ""
echo "  Demo gate:   See deployment/platinum_demo.md"
