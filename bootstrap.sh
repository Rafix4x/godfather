#!/usr/bin/env bash
set -uo pipefail

REPO="${GODFATHER_REPO:-Rafix4x/godfather}"
BRANCH="${GODFATHER_BRANCH:-main}"
ROOT="${GODFATHER_HOME:-$HOME/.godfather}"
TARBALL_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

RUN_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --install) RUN_INSTALL=1 ;;
    --help|-h)
      printf 'usage: bash bootstrap.sh [--install]\n'
      printf '  --install   install into the detected agents right away\n'
      exit 0
      ;;
  esac
done

log() { printf '  %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
  || die "need curl or wget"

IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *com.termux* ]]; then
  IS_TERMUX=1
elif [[ -d /data/data/com.termux ]]; then
  IS_TERMUX=1
fi

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
fi

mkdir -p "$ROOT"

tmp="$(mktemp -d 2>/dev/null || mktemp -d -t godfather)"
[[ -d "$tmp" ]] || die "cannot create a temporary directory"
trap 'rm -rf "$tmp"' EXIT

log "downloading ${REPO}@${BRANCH}"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$TARBALL_URL" -o "$tmp/pkg.tar.gz" || die "download failed"
else
  wget -qO "$tmp/pkg.tar.gz" "$TARBALL_URL" || die "download failed"
fi

tar xzf "$tmp/pkg.tar.gz" -C "$tmp" || die "extract failed"
src="$(find "$tmp" -maxdepth 1 -mindepth 1 -type d | head -1)"
[[ -d "$src" ]] || die "unexpected archive layout"

log "installing to $ROOT"
find "$ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null
cp -r "$src"/. "$ROOT"/ || die "copy failed"

chmod +x "$ROOT/install.sh" "$ROOT/install-termux.sh" "$ROOT/install-mcp.sh" \
  "$ROOT/verify.sh" "$ROOT/gf" 2>/dev/null
chmod +x "$ROOT/scripts"/*.py 2>/dev/null

if [[ $RUN_INSTALL -eq 1 ]]; then
  if [[ $IS_TERMUX -eq 1 ]]; then
    log "running the Termux installer"
    bash "$ROOT/install-termux.sh" || die "install failed"
  else
    log "running the installer"
    bash "$ROOT/install.sh" --project "$PWD" || die "install failed"
  fi
  log ""
fi

if [[ $IS_TERMUX -eq 1 ]]; then
  cat <<'NEXT'

Termux detected.

Next:
  pkg install python git curl          # python3 is often missing here
  termux-setup-storage                 # only for projects outside $HOME
  bash ~/.godfather/install-termux.sh  # install into the agents on this device

  python ~/.godfather/scripts/selftest.py
  python ~/.godfather/scripts/relay.py "your request"

NEXT
  exit 0
fi

if [[ -z "$PY" ]]; then
  cat <<'NEXT'

Next:
  install Python 3.9 or newer, then:
  bash ~/.godfather/install.sh

NEXT
  exit 0
fi

cat <<NEXT

Next:
  bash ~/.godfather/install.sh --dry-run     # preview
  bash ~/.godfather/install.sh               # install into your agents
  bash ~/.godfather/install.sh --uninstall   # undo

  $PY ~/.godfather/scripts/selftest.py       # offline checks
  bash ~/.godfather/install-mcp.sh           # register the MCP server

NEXT
