#!/usr/bin/env bash
# verify — L2 smoke test after restore. Hits each expected local port.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check() {
  local url="$1"; local expect="${2:-}"; local flag="${3:-}"
  local out body
  out=$(curl -sS $flag --max-time 5 -o /tmp/verify.$$ -w '%{http_code}' "$url" 2>/dev/null || echo "000")
  body=$(cat /tmp/verify.$$ 2>/dev/null || echo ""); rm -f /tmp/verify.$$
  if [[ "$out" =~ ^[23] ]] && { [ -z "$expect" ] || echo "$body" | grep -qF "$expect"; }; then
    printf '[ok]   %s → %s\n' "$url" "$out"
    return 0
  fi
  printf '[fail] %s → %s\n' "$url" "$out"
  return 1
}

pass=0; fail=0
run() { if check "$@"; then pass=$((pass+1)); else fail=$((fail+1)); fi }

run https://localhost:9090/ping     ""      -k
run http://localhost:2283/api/server/ping '"pong"'
run http://localhost:15678/healthz  '"ok"'
run http://localhost:8123/manifest.json
run http://localhost:18787/
run http://localhost:19119/
run http://localhost:18642/v1/models
run http://localhost:8888/
run http://localhost:8081/v1/health
run http://localhost:3000/

echo
echo "── summary: $pass ok, $fail fail ──"
[ "$fail" -eq 0 ]
