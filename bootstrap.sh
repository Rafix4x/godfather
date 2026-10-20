#!/usr/bin/env bash
set -uo pipefail

REPO="${GODFATHER_REPO:-Rafix4x/godfather}"
BRANCH="${GODFATHER_BRANCH:-main}"
ROOT="${GODFATHER_HOME:-$HOME/.godfather}"
TARBALL_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

log() { printf '  %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
  || die "need curl or wget"

mkdir -p "$ROOT"

tmp="$(mktemp -d)"
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
if [[ -d "$ROOT" ]]; then
  find "$ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
cp -r "$src"/. "$ROOT"/ || die "copy failed"

chmod +x "$ROOT/install.sh" 2>/dev/null
chmod +x "$ROOT/scripts"/*.py 2>/dev/null
mkdir -p "$ROOT/scripts" && cp -r "$ROOT/scripts" "$ROOT/.scripts_tmp" 2>/dev/null
rm -rf "$ROOT/.scripts_tmp"

cat <<'NEXT'

Next:
  bash ~/.godfather/install.sh --dry-run     # preview
  bash ~/.godfather/install.sh               # install into your agents
  bash ~/.godfather/install.sh --uninstall   # undo

NEXT
