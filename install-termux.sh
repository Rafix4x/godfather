#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_HOME="${GODMODE_TARGET_HOME:-$HOME}"
PROJECT_DIR="${GODMODE_PROJECT_DIR:-$PWD}"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  printf '%s\n' "error: no Python found." "Install it first:  pkg install python" >&2
  exit 2
fi

IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *com.termux* ]]; then
  IS_TERMUX=1
elif [[ -d /data/data/com.termux ]]; then
  IS_TERMUX=1
fi

log() { printf '%s\n' "$*"; }

log "Godfather installer for Termux / Android"

if [[ ! -f "$HERE/install.sh" ]]; then
  log "error: install.sh not found next to this script" >&2
  exit 2
fi

log ""
log "installing into $TARGET_HOME/.godfather"
if [[ -d "$TARGET_HOME/.godfather" ]]; then
  log "  existing install found, refreshing it"
fi
mkdir -p "$TARGET_HOME/.godfather"
for item in install.sh bootstrap.sh SKILL.md README.md gf verify.sh install-mcp.sh; do
  [[ -f "$HERE/$item" ]] && cp -f "$HERE/$item" "$TARGET_HOME/.godfather/$item"
done
[[ -d "$HERE/scripts" ]] && mkdir -p "$TARGET_HOME/.godfather/scripts" \
  && cp -f "$HERE/scripts/"*.py "$TARGET_HOME/.godfather/scripts/"
[[ -d "$HERE/adapters" ]] && mkdir -p "$TARGET_HOME/.godfather/adapters" \
  && cp -f "$HERE/adapters/"*.md "$TARGET_HOME/.godfather/adapters/"
[[ -d "$HERE/references" ]] && mkdir -p "$TARGET_HOME/.godfather/references" \
  && cp -rf "$HERE/references/." "$TARGET_HOME/.godfather/references/"

log "  core files copied"

bash "$HERE/install.sh" --no-detect --target-home "$TARGET_HOME" --project "$PROJECT_DIR" \
  2>&1 | sed 's/^/  /'

log ""
if [[ $IS_TERMUX -eq 1 ]]; then
  log "Termux detected."
  log ""
  log "Next steps:"
  log "  1. Required packages:"
  log "       pkg install python git curl"
  log "  2. Give the shell access to shared storage (only needed for"
  log "     projects outside \$HOME):"
  log "       termux-setup-storage"
  log "  3. Check the install:"
  log "       python \$HOME/.godfather/scripts/selftest.py"
  log "  4. Run the relay:"
  log "       python \$HOME/.godfather/scripts/relay.py \"your request\""
  log ""
  log "Note: python3 may be absent on Termux. Use python everywhere."
  log "Note: agents that need a desktop GUI do not run under Termux, but"
  log "      the relay, the resolver and the skill files all do."
else
  log "Next steps:"
  log "  1. Check the install:"
  log "       $PY $TARGET_HOME/.godfather/scripts/selftest.py"
  log "  2. Run the relay:"
  log "       $PY $TARGET_HOME/.godfather/scripts/relay.py \"your request\""
  log "  3. Restart your agent session so the rules load."
fi

log ""
log "done."
