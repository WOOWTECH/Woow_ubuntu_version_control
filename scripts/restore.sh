#!/usr/bin/env bash
# restore — replay a host's state from its folder + a backup tar.
#
# Preconditions:
#   1. `ubuntu-skills/podman-host-bootstrap` has been run (podman, cockpit,
#      linger, subuid all present).
#   2. Backup tar exists at /tmp/backup-<host>.tar.zst (override with TAR=...).
#      Its sha256 will be verified against snapshot-manifest.md.
#   3. External secrets have been collected — run scripts/list-secrets.sh first.
#
# Usage:
#   restore.sh <host-folder>
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

host_dir_arg="${1:?usage: restore.sh <host-folder>}"
repo_root="$(dirname "$here")"
host_dir="$repo_root/$host_dir_arg"
[ -d "$host_dir" ] || { echo "Not found: $host_dir" >&2; exit 1; }

host_name="$(basename "$host_dir")"
default_tar="/tmp/backup-${host_name}.tar.zst"
TAR="${TAR:-$default_tar}"

echo "═══ restore ═══"
echo "host_dir : $host_dir"
echo "tar      : $TAR"
echo

# ── 1. Preflight — expect ubuntu-skills bootstrap already done
echo "[1/6] preflight"
for bin in podman podman-compose git curl zstd tar; do
  command -v "$bin" >/dev/null || { echo "  ! missing $bin — run ubuntu-skills/podman-host-bootstrap first" >&2; exit 1; }
done
echo "  ↳ ok"

# ── 2. Verify backup tar
mf="$host_dir/snapshot-manifest.md"
if [ ! -f "$TAR" ]; then
  echo "[2/6] tar missing: $TAR"
  echo "  Expected sha256:"
  grep -m1 '^| sha256 |' "$mf" 2>/dev/null || echo "  (no manifest)"
  echo "  Copy the tar there and re-run, or set TAR=/path/to/tar."
  exit 2
fi
echo "[2/6] verifying tar"
have=$(sha256sum "$TAR" | awk '{print $1}')
want=$(awk -F'|' '/^\| sha256 \|/{gsub(/ /,"",$3); print $3; exit}' "$mf" 2>/dev/null || echo "")
if [ -n "$want" ] && [ "$have" != "$want" ]; then
  echo "  ! sha256 mismatch"
  echo "    have $have"
  echo "    want $want"
  exit 3
fi
echo "  ↳ ok ($have)"

# ── 3. Extract tar
echo "[3/6] extracting"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar --zstd -xf "$TAR" -C "$tmp"

# 3a. Restore user files by copying each entry back to its absolute source
# (the tar was made with absolute paths — tar preserves them).
# Only the pgdumps/podman-volumes subdirs are relative and need special handling.
for p in "$HOME/.config/systemd/user" "$HOME/.cloudflared" "$HOME/ha-config" \
         "$HOME/matter-server-data"; do
  src="${tmp}${p}"
  if [ -d "$src" ]; then
    mkdir -p "$p"
    cp -a "$src/." "$p/"
    echo "  ↳ restored $p"
  fi
done
# Individual .env files: same trick
find "$tmp" -name .env -o -name .claude-oauth.env -o -name docker-compose.yml -o -name run-host.sh 2>/dev/null | while read -r f; do
  rel="${f#$tmp}"
  mkdir -p "$(dirname "$rel")"
  cp -f "$f" "$rel"
  chmod 600 "$rel" 2>/dev/null || true
  echo "  ↳ restored $rel"
done

# ── 4. Restore podman volumes (from the exported tars)
echo "[4/6] restoring podman volumes"
if [ -d "$tmp/podman-volumes" ]; then
  for vt in "$tmp/podman-volumes/"*.tar; do
    [ -f "$vt" ] || continue
    vname="$(basename "$vt" .tar)"
    if ! podman volume exists "$vname" 2>/dev/null; then
      podman volume create "$vname" >/dev/null
    fi
    podman volume import "$vname" "$vt" 2>/dev/null && echo "  ↳ ${vname}"
  done
fi

# ── 5. Pull images and start each compose stack
echo "[5/6] deploying services"
# Re-clone the code repos listed in install-list.md if their dirs don't exist.
awk '/^\| ~\// {gsub(/\|/," "); print $2, $3}' "$host_dir/install-list.md" 2>/dev/null \
  | while read -r rel remote; do
      [ -z "${rel:-}" ] && continue
      dir="${HOME}/${rel#~/}"
      if [ ! -d "$dir/.git" ] && [ "$remote" != "-" ] && [ -n "$remote" ]; then
        git clone "$remote" "$dir" 2>/dev/null && echo "  ↳ cloned $remote → $dir"
      fi
    done

# For every compose file discovered, run `podman-compose up -d`.
# Order matters: cf-tunnel & webgui first, then apps, then vibe-kanban.
run_compose() {
  local dir="$1"
  [ -f "$dir/docker-compose.yml" ] || return 0
  echo "  ↳ compose up in $dir"
  (cd "$dir" && podman-compose up -d 2>&1 | tail -3)
}
for d in Woow_cloudflare_tunnel_webgui Woow_immich_docker_compose_all \
         Woow_n8n_docker_compose_all Woow_ha_ai_mcp \
         hermes_deploy/hermes/podman vibe-kanban-stack; do
  full="$HOME/$d"
  [ -d "$full" ] && run_compose "$full"
done

# ── 6. Install systemd user units
echo "[6/6] enabling systemd user units"
systemctl --user daemon-reload
for f in "$host_dir/systemd-units/"*.service; do
  [ -f "$f" ] || continue
  cp -f "$f" "$HOME/.config/systemd/user/"
  systemctl --user enable "$(basename "$f")" 2>/dev/null || true
done
systemctl --user daemon-reload

echo
echo "═══ restore done ═══"
echo "Next: bash scripts/verify.sh $host_dir_arg"
