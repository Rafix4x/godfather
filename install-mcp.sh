#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${GODFATHER_HOME:-$HOME/.godfather}"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: no python interpreter found" >&2
  exit 1
fi

if [[ -d "$HERE/scripts" ]]; then
  SCRIPTS="$HERE/scripts"
else
  SCRIPTS="$ROOT/scripts"
fi

MCP="$SCRIPTS/mcp_server.py"
[[ -f "$MCP" ]] || { echo "error: mcp_server.py not found in $SCRIPTS" >&2; exit 1; }

TARGET_HOME="${GODMODE_TARGET_HOME:-$HOME}"
DRY=0
AGENT_FILTER=""

usage() {
  cat <<'USAGE'
Register the godfather MCP server with your agents.

Usage:
  bash install-mcp.sh [options]

Options:
  --dry-run          Print planned writes, change nothing
  --agents a,b       Restrict to specific agents
  --target-home DIR  Register under a different home
  -h, --help         Show this help

Registered agents:
  claude-code  cursor  windsurf  cline  roo  continue  opencode
USAGE
}

log() { printf '  %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY=1; shift ;;
    --agents)      AGENT_FILTER="${2:-}"; shift 2 ;;
    --target-home) TARGET_HOME="${2:-}"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *)             die "unknown flag: $1 (try --help)" ;;
  esac
done

want_agent() {
  [[ -z "$AGENT_FILTER" ]] && return 0
  [[ ",$AGENT_FILTER," == *",$1,"* ]]
}

SERVER_CMD="\"$PY\" \"$MCP\""

register_json() {
  local file="$1" key="$2"
  if [[ $DRY -eq 1 ]]; then
    log "would register mcp server '$key' -> $file"
    return 0
  fi
  mkdir -p "$(dirname "$file")"
  [[ -f "$file" ]] && cp -p "$file" "$file.bak.godmode" 2>/dev/null
  "$PY" - "$file" "$key" "$PY" "$MCP" <<'PYEOF'
import json, os, sys
path, key, py, script = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
data = {}
if os.path.exists(path):
    raw = open(path, encoding="utf-8").read().strip()
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
servers = data.setdefault("mcpServers", {})
servers[key] = {"command": py, "args": [script]}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PYEOF
  log "registered '$key' -> $file"
}

register_claude_code() {
  want_agent claude-code || return 0
  register_json "$TARGET_HOME/.claude.json" godfather
}
register_cursor() {
  want_agent cursor || return 0
  register_json "$TARGET_HOME/.cursor/mcp.json" godfather
}

register_windsurf() {
  want_agent windsurf || return 0
  register_json "$TARGET_HOME/.codeium/windsurf/mcp_config.json" godfather
}

register_cline() {
  want_agent cline || return 0
  register_json "$TARGET_HOME/.cline/mcp.json" godfather
}

register_roo() {
  want_agent roo || return 0
  register_json "$TARGET_HOME/.roo/mcp.json" godfather
}

register_continue() {
  want_agent continue || return 0
  register_json "$TARGET_HOME/.continue/config.json" godfather
}

register_opencode() {
  want_agent opencode || return 0
  local file="$TARGET_HOME/.config/opencode/opencode.json"
  if [[ $DRY -eq 1 ]]; then
    log "would register mcp server 'godfather' -> $file"
    return 0
  fi
  mkdir -p "$(dirname "$file")"
  [[ -f "$file" ]] && cp -p "$file" "$file.bak.godmode" 2>/dev/null
  "$PY" - "$file" "$PY" "$MCP" <<'PYEOF'
import json, os, sys
path, py, script = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(path):
    raw = open(path, encoding="utf-8").read().strip()
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
servers = data.setdefault("mcp", {})
servers["godfather"] = {"type": "local", "command": [py, script], "enabled": True}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PYEOF
  log "registered 'godfather' -> $file"
}

echo "godfather MCP registration"
echo "  home: $TARGET_HOME"
[[ $DRY -eq 1 ]] && echo "  MODE: dry-run"
echo ""

for agent in claude-code cursor windsurf cline roo continue opencode; do
  fn="register_$(printf '%s' "$agent" | tr '-' '_')"
  "$fn"
done

echo ""
if [[ $DRY -eq 1 ]]; then
  echo "dry-run complete"
else
  echo "registered. Restart your agent session to load the tools."
  echo "tools: godfather_relay, godfather_reframe, godfather_clean, godfather_providers, godfather_guard"
fi
