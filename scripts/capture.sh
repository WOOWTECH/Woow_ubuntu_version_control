#!/usr/bin/env bash
# capture — scan this host and produce {host-folder}/{install-list,system-manifest,snapshot-manifest}.md
# plus copy systemd-units/ + cloudflared-config/ + compose/ files, and produce a
# backup tar in $BACKUP_DEST (default ~/.backups/). Only markdown/config lands
# under git; the tar is .gitignored.
#
# Usage:
#   capture.sh <host-folder-name>          e.g. 1-N100-toypark1234
#
# Environment:
#   BACKUP_DEST     directory to write backup tar   (default: ~/.backups)
#   STOP_SERVICES   1=cold backup (stop podman user units), 0=hot   (default: 1)
#   SKIP_TAR        1=skip creating backup tar                       (default: 0)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lib="$here/lib"
repo_root="$(dirname "$here")"

host="${1:?usage: capture.sh <host-folder-name>}"
host_dir="$repo_root/$host"
mkdir -p "$host_dir/compose"

BACKUP_DEST="${BACKUP_DEST:-$HOME/.backups}"
STOP_SERVICES="${STOP_SERVICES:-1}"
SKIP_TAR="${SKIP_TAR:-0}"
mkdir -p "$BACKUP_DEST"

timestamp=$(date +%Y%m%d-%H%M%S)
tar_path="$BACKUP_DEST/backup-${host}-${timestamp}.tar.zst"

echo "═══ capture ═══"
echo "host       : $host"
echo "host_dir   : $host_dir"
echo "tar_dest   : $tar_path"
echo "cold       : ${STOP_SERVICES}"
echo

# ── 1. install-list.md ─────────────────────────────────────
echo "[1/6] install-list.md"
{
  echo "# Home Assistant Resources — ${host}"
  echo
  echo "Last scanned: $(date -Iseconds)"
  echo
  bash "$lib/inventory-apt.sh"
  bash "$lib/inventory-podman.sh"
  bash "$lib/inventory-systemd.sh" "$host_dir"
  bash "$lib/inventory-native.sh"
  bash "$lib/inventory-repos.sh"
  bash "$lib/inventory-cloudflared.sh" "$host_dir"
} > "$host_dir/install-list.md"

# ── 2. system-manifest.md ──────────────────────────────────
echo "[2/6] system-manifest.md"
{
  echo "# System Manifest — ${host}"
  echo
  echo "## Host Identity"
  echo
  echo "| Key | Value |"
  echo "|-----|-------|"
  echo "| hostname | $(hostname) |"
  echo "| static hostname | $(hostnamectl --static 2>/dev/null || echo -) |"
  echo "| machine-id | $(cat /etc/machine-id 2>/dev/null || echo -) |"
  echo "| CPU | $(lscpu | awk -F: '/Model name/{gsub(/^ +/,"",$2); print $2; exit}') |"
  echo "| Cores | $(nproc) |"
  echo "| RAM | $(free -h | awk '/^Mem:/ {print $2}') |"
  echo "| Disk / | $(df -h / | awk 'NR==2 {print $2" total, "$3" used, "$4" avail"}') |"
  echo "| OS | $(. /etc/os-release; echo "$PRETTY_NAME") |"
  echo "| Kernel | $(uname -r) |"
  echo "| Architecture | $(uname -m) |"
  echo "| Linger | $(loginctl show-user "$USER" 2>/dev/null | awk -F= '/^Linger/{print $2}') |"
  echo
  echo "## Compose Files (source of truth)"
  echo
  echo "| Service | Path | Copied to |"
  echo "|---------|------|-----------|"
  # Discover compose files under $HOME
  found=0
  while read -r cf; do
    rel="${cf#$HOME/}"
    name=$(dirname "$rel" | sed 's|/|_|g')
    dest="compose/${name}.yml"
    cp -f "$cf" "$host_dir/$dest"
    printf '| %s | ~/%s | %s |\n' "$name" "$rel" "$dest"
    found=$((found+1))
  done < <(find "$HOME" -maxdepth 4 -name docker-compose.yml -o -name podman-compose.yml 2>/dev/null \
    | grep -Ev '/(node_modules|\.cargo|\.rustup|target|\.claude|\.local|\.cache|\.nvm)/' | sort)
  [ "$found" -eq 0 ] && echo "| (none found) | - | - |"
  echo
  echo "## External Secrets Required"
  echo
  echo "These must be provided when restoring on a new host. \`scripts/list-secrets.sh\` prints"
  echo "the same list interactively."
  echo
  cat <<'SEC'
| Key | Used by | How to obtain | Where to place |
|-----|---------|---------------|----------------|
| `ANTHROPIC_API_KEY` | Hermes, VK host | https://console.anthropic.com/ | ~/hermes_deploy/hermes/podman/.env, ~/vibe-kanban-stack/.claude-oauth.env |
| `MINIMAX_API_KEY` | Hermes | MiniMax platform | ~/hermes_deploy/hermes/podman/.env |
| `HOMEASSISTANT_TOKEN` | HA-MCP | HA → Profile → Long-Lived Tokens (after HA up) | ~/Woow_ha_ai_mcp/.env |
| `CF_API_TOKEN` | cf tunnel routes | Cloudflare dash → API Tokens (Zone.DNS.Edit + Account.Tunnel.Edit) | ~/.homelab/secrets.env |
| `CF_ACCOUNT_ID` | cf tunnel | Cloudflare dash right sidebar | ~/.homelab/secrets.env |
| `CF_ZONE` | cf tunnel routes | e.g. `example.com` | ~/.homelab/secrets.env |
| Claude OAuth JSON | VK host | Copy from a machine already logged in (`~/.claude-oauth.json`) | ~/vibe-kanban-stack/.claude-oauth.env |
| `SELF_HOST_LOCAL_AUTH_EMAIL/PASSWORD` | VK stack | Choose your own admin creds | ~/vibe-kanban-stack/.env |
SEC
  echo
  echo "## Ports Exposed (host bindings)"
  echo
  echo "| Port | Process/Container |"
  echo "|------|-------------------|"
  ss -tlnH 2>/dev/null | awk '{split($4,a,":"); print a[length(a)]}' | sort -un | while read -r p; do
    who=$(ss -tlnpH sport = ":$p" 2>/dev/null | head -1 | awk -F'users:' '{print $2}' | head -c 120)
    printf '| %s | %s |\n' "$p" "${who:--}"
  done
  echo
} > "$host_dir/system-manifest.md"

# ── 3. wish-list.md (only create if missing; user edits by hand) ────
if [ ! -f "$host_dir/wish-list.md" ]; then
  echo "[3/6] wish-list.md (initial placeholder)"
  cat > "$host_dir/wish-list.md" <<WISH
# Wishlist — ${host}

Services / features planned but not yet built. Edit by hand.

| # | Item | Notes |
|---|------|-------|
| 1 | (add here) | |
WISH
else
  echo "[3/6] wish-list.md exists — left untouched"
fi

# ── 4. Backup tar ──────────────────────────────────────────
if [ "$SKIP_TAR" = "1" ]; then
  echo "[4/6] backup tar — SKIP_TAR=1, skipping"
else
  echo "[4/6] backup tar"
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT

  # 4a. Cold or hot?
  if [ "$STOP_SERVICES" = "1" ]; then
    echo "  ↳ stopping podman user units (cold backup)"
    for u in $(systemctl --user list-units --type=service --all --plain --no-legend 2>/dev/null \
                | awk '$1 ~ /^podman-/ || $1 == "vibe-kanban-host.service" {print $1}'); do
      systemctl --user stop "$u" 2>/dev/null || true
    done
  fi

  # 4b. Postgres logical dumps (do this BEFORE stopping is a subtle race; we
  # actually restart briefly if cold mode was on)
  if [ "$STOP_SERVICES" = "1" ]; then
    for u in podman-immich.service podman-n8n.service podman-hermes.service; do
      systemctl --user start "$u" 2>/dev/null || true
    done
    sleep 5
  fi
  mkdir -p "$work/pgdumps"
  bash "$lib/dump-postgres.sh" "$work/pgdumps"
  if [ "$STOP_SERVICES" = "1" ]; then
    for u in podman-immich.service podman-n8n.service podman-hermes.service; do
      systemctl --user stop "$u" 2>/dev/null || true
    done
  fi

  # 4c. Assemble file list (sensitive stuff — never in git)
  cat > "$work/files.list" <<LST
$HOME/.config/systemd/user
$HOME/.cloudflared
$HOME/ha-config
$HOME/matter-server-data
$HOME/Woow_immich_docker_compose_all/.env
$HOME/Woow_n8n_docker_compose_all/.env
$HOME/Woow_ha_ai_mcp/.env
$HOME/Woow_cloudflare_tunnel_webgui/.env
$HOME/hermes_deploy/hermes/podman/.env
$HOME/vibe-kanban-stack/.env
$HOME/vibe-kanban-stack/.claude-oauth.env
$HOME/vibe-kanban-stack/docker-compose.yml
$HOME/vibe-kanban-stack/run-host.sh
LST
  # 4d. Podman volume export (each running volume)
  mkdir -p "$work/podman-volumes"
  for v in $(podman volume ls -q 2>/dev/null); do
    podman volume export "$v" > "$work/podman-volumes/${v}.tar" 2>/dev/null || true
  done

  # 4e. Create tar (zstd -19 for good ratio, adjust if too slow)
  echo "  ↳ packing into $tar_path"
  tar --zstd -cf "$tar_path" \
    --files-from=<(grep -v '^$' "$work/files.list") \
    -C "$work" pgdumps podman-volumes 2>/tmp/tar-warnings.$$ || {
      echo "  ! tar warnings (see /tmp/tar-warnings.$$):"; head -20 /tmp/tar-warnings.$$ >&2
    }

  # 4f. Restart services if we stopped them
  if [ "$STOP_SERVICES" = "1" ]; then
    echo "  ↳ restarting podman user units"
    for u in $(systemctl --user list-unit-files --type=service --state=enabled 2>/dev/null \
                | awk '$1 ~ /^podman-/ || $1 == "vibe-kanban-host.service" {print $1}'); do
      systemctl --user start "$u" 2>/dev/null || true
    done
  fi

  # 4g. snapshot-manifest
  sha=$(sha256sum "$tar_path" | awk '{print $1}')
  sz=$(stat -c%s "$tar_path")
  szh=$(numfmt --to=iec --suffix=B "$sz" 2>/dev/null || echo "$sz")
  {
    echo "# Snapshot Manifest — ${host}"
    echo
    echo "| Key | Value |"
    echo "|-----|-------|"
    echo "| filename | $(basename "$tar_path") |"
    echo "| path (source host) | $tar_path |"
    echo "| size | $szh |"
    echo "| sha256 | $sha |"
    echo "| created | $(date -Iseconds) |"
    echo "| host | $host |"
    echo
    echo "Backup is **not** tracked by git. Copy the tar to the target host"
    echo "(default \`/tmp/backup-${host}.tar.zst\`) before running \`scripts/restore.sh\`."
  } > "$host_dir/snapshot-manifest.md"
fi

echo "[5/6] done — files in $host_dir/:"
ls -la "$host_dir"
echo
echo "[6/6] next steps:"
echo "  git add \"$host\"/"
echo "  git commit -m \"capture: $host @ $timestamp\""
echo "  (backup tar at $tar_path is NOT committed)"
