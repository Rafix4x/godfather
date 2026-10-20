#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd)"
[[ -n "$HERE" && "$HERE" != "${BASH_SOURCE[0]}" ]] || HERE="$PWD"
exec bash "$HERE/install.sh" "$@"
