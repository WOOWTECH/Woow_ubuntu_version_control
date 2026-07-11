#!/usr/bin/env bash
# list-secrets — extract the "External Secrets Required" table from a host's
# system-manifest.md and print it as an actionable checklist.
set -euo pipefail
host_dir="${1:?usage: list-secrets.sh <host-folder>}"
mf="$host_dir/system-manifest.md"
[ -f "$mf" ] || { echo "Not found: $mf" >&2; exit 1; }

echo "── External secrets required for ${host_dir} ──"
awk '
  /^## External Secrets Required/ { on=1; next }
  on && /^## / { exit }
  on { print }
' "$mf"
echo
echo "Set each of the above before running scripts/restore.sh."
