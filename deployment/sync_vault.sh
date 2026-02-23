#!/usr/bin/env bash
# sync_vault.sh — Git-based vault sync between local machine and cloud VM
#
# Secrets are excluded via .gitignore (secrets/, .env).
# Only vault content and code changes are synced.
#
# Usage:
#   ./deployment/sync_vault.sh push    # commit & push local changes to GitHub
#   ./deployment/sync_vault.sh pull    # pull latest from GitHub (on VM or local)
#   ./deployment/sync_vault.sh status  # show what would be committed

set -euo pipefail
IFS=$'\n\t'

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[sync]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

COMMAND="${1:-status}"

# ── Verify git repo ───────────────────────────────────────────────────────────
if ! git rev-parse --git-dir &>/dev/null; then
    die "Not a git repository. Run: git init && git remote add origin <YOUR_GITHUB_URL>"
fi

# ── Verify remote is configured ──────────────────────────────────────────────
if ! git remote get-url origin &>/dev/null; then
    die "No git remote 'origin' configured. Run:\n  git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
fi

# ── Confirm secrets are not tracked ──────────────────────────────────────────
tracked_secrets=$(git ls-files secrets/ .env 2>/dev/null || true)
if [ -n "$tracked_secrets" ]; then
    die "SECRET FILES ARE TRACKED BY GIT:\n$tracked_secrets\nRun: git rm --cached <file> and add to .gitignore"
fi

case "$COMMAND" in

  # ────────────────────────────────────────────────────────────────────────────
  push)
    info "Staging vault and code changes..."

    # Stage everything except secrets (already in .gitignore)
    git add \
        vault/ \
        watchers/ \
        scheduler/ \
        mcp-servers/ \
        setup/ \
        .claude/ \
        deployment/ \
        requirements.txt \
        CLAUDE.md \
        README.md \
        .env.example \
        .gitignore 2>/dev/null || true

    # Check if there's anything to commit
    if git diff --cached --quiet; then
        info "Nothing to commit — vault is already up to date"
        exit 0
    fi

    # Show what's being committed
    info "Changes to be committed:"
    git diff --cached --stat

    # Commit with timestamp
    TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    git commit -m "vault sync: $TIMESTAMP

Auto-sync from ai-employee agent.
Secrets excluded per .gitignore."

    # Push
    info "Pushing to origin/main..."
    git push origin main
    info "Sync complete — vault pushed to GitHub"
    ;;

  # ────────────────────────────────────────────────────────────────────────────
  pull)
    info "Pulling latest from origin/main..."

    # Stash any local uncommitted changes to avoid conflicts
    STASH_MSG="sync-pull-stash-$(date +%s)"
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Stashing local uncommitted changes as: $STASH_MSG"
        git stash push -m "$STASH_MSG"
        STASHED=true
    else
        STASHED=false
    fi

    git pull --rebase origin main

    if [ "$STASHED" = true ]; then
        info "Restoring stashed changes..."
        git stash pop || warn "Stash pop had conflicts — resolve manually with: git stash show -p"
    fi

    info "Pull complete — vault is up to date"
    ;;

  # ────────────────────────────────────────────────────────────────────────────
  status)
    info "Git status (secrets excluded):"
    git status --short
    echo ""
    info "Remote:"
    git remote -v
    echo ""
    info "Last 5 commits:"
    git log --oneline -5
    ;;

  *)
    die "Unknown command: $COMMAND\nUsage: sync_vault.sh [push|pull|status]"
    ;;

esac
