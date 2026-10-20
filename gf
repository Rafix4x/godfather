#!/usr/bin/env bash
set -uo pipefail

ROOT="${GODFATHER_HOME:-$HOME/.godfather}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "$HERE/scripts" ]]; then
  SCRIPTS="$HERE/scripts"
elif [[ -d "$HOME/.godfather/scripts" ]]; then
  SCRIPTS="$HOME/.godfather/scripts"
else
  SCRIPTS="$HERE"
fi

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: no python interpreter found. Install one (apt install python3, brew install python, pkg install python)." >&2
  exit 1
fi

INSTALL="$SCRIPTS/../install.sh"
[[ -f "$INSTALL" ]] || INSTALL="$HERE/install.sh"

usage() {
  cat <<'USAGE'
godfather - unrestricted operator mode for your coding agents

Usage:
  gf relay <request>        Answer through your own provider, no refusal
  gf reframe <request>      Print the refusal-free reframed request
  gf clean <text>           Strip refusals and hedges from text
  gf providers              List detected providers (keys masked)
  gf install [flags]        Run the installer
  gf uninstall              Remove installed blocks
  gf verify                 Run the self-verifying claims harness
  gf canary [--canary all]  Raw-vs-framed refusal canary
  gf mcp                    Run the MCP server on stdio
  gf version                Show version

Flags for relay:
  --agent <name>            Resolve one agent's provider
  --frame <name>            card | pro | dual | artifact | direct
  --provider-scan           Sweep every model on the provider
  --json                    Machine-readable output

Examples:
  gf relay "how do I capture a WPA2 handshake on my own network"
  gf relay --agent codex --frame pro "write a keylogger in C"
  gf providers
USAGE
}

case "${1:-}" in
  relay)
    shift
    exec "$PY" "$SCRIPTS/relay.py" "$@"
    ;;
  reframe)
    shift
    exec "$PY" "$SCRIPTS/parseltongue.py" "$@"
    ;;
  clean)
    shift
    exec "$PY" "$SCRIPTS/refusal_scan.py" --clean --file /dev/stdin "$@"
    ;;
  providers)
    shift
    exec "$PY" "$SCRIPTS/provider_resolve.py" "$@"
    ;;
  install)
    shift
    exec bash "$INSTALL" "$@"
    ;;
  uninstall)
    shift
    exec bash "$INSTALL" --uninstall "$@"
    ;;
  verify)
    shift
    exec "$PY" "$SCRIPTS/verify_claims.py" "$@"
    ;;
  canary)
    shift
    exec "$PY" "$SCRIPTS/godmode_check.py" "$@"
    ;;
  mcp)
    shift
    exec "$PY" "$SCRIPTS/mcp_server.py" "$@"
    ;;
  version)
    echo "godfather 1.0.0"
    echo "  home: $ROOT"
    echo "  scripts: $SCRIPTS"
    echo "  python: $PY"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "error: unknown command: $1" >&2
    echo "" >&2
    usage >&2
    exit 2
    ;;
esac
