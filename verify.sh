#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd)"
[[ -n "$ROOT" && "$ROOT" != "${BASH_SOURCE[0]}" ]] || ROOT="$PWD"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: python3 or python is required" >&2
  exit 2
fi

FAILED=0

echo "== shell syntax =="
for script in install.sh bootstrap.sh gf install-mcp.sh verify.sh; do
  [ -f "$script" ] || continue
  if bash -n "$script" 2>/dev/null; then
    echo "PASS  $script"
  else
    echo "FAIL  $script"
    bash -n "$script" || true
    FAILED=1
  fi
done

echo
echo "== python syntax =="
for module in scripts/*.py; do
  if "$PY" -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())" "$module" 2>/dev/null; then
    echo "PASS  $module"
  else
    echo "FAIL  $module"
    "$PY" -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())" "$module" || true
    FAILED=1
  fi
done

echo
echo "== selftest =="
if "$PY" scripts/selftest.py; then
  :
else
  FAILED=1
fi

echo
echo "== claims =="
if "$PY" scripts/verify_claims.py; then
  :
else
  FAILED=1
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "RESULT: PASS"
  exit 0
fi
echo "RESULT: FAIL"
exit 1
