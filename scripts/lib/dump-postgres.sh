#!/usr/bin/env bash
# dump-postgres — run pg_dumpall against every running postgres-flavoured
# container, writing SQL dumps to <out-dir>.
# Usage:
#   dump-postgres.sh <out-dir>
set -euo pipefail
out="$1"
mkdir -p "$out"

# Detect postgres containers by image name substring
mapfile -t pg_names < <(
  podman ps --format '{{.Names}}\t{{.Image}}' 2>/dev/null \
    | awk -F'\t' 'tolower($2) ~ /postgres|timescale/ {print $1}'
)

if [ ${#pg_names[@]} -eq 0 ]; then
  echo "[dump-postgres] no postgres containers found"
  exit 0
fi

for c in "${pg_names[@]}"; do
  # Grab superuser from env vars
  user=$(podman inspect "$c" --format \
    '{{range .Config.Env}}{{if or (eq (index (split . "=") 0) "POSTGRES_USER") (eq (index (split . "=") 0) "PGUSER")}}{{println .}}{{end}}{{end}}' \
    2>/dev/null | head -1 | cut -d= -f2)
  user="${user:-postgres}"
  file="${out}/${c}.sql.gz"
  echo "[dump-postgres] ${c} (user=${user}) → ${file}"
  if ! podman exec "$c" pg_dumpall -U "$user" 2>/dev/null | gzip > "$file"; then
    echo "  ! failed"
    rm -f "$file"
  fi
done
