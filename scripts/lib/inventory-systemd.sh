#!/usr/bin/env bash
# inventory-systemd — list user systemd unit files + copy them to host folder.
# Usage:
#   inventory-systemd.sh <host-folder>
# Writes markdown to stdout and copies each ~/.config/systemd/user/*.service to
#   <host-folder>/systemd-units/
set -euo pipefail
host_dir="$1"
mkdir -p "${host_dir}/systemd-units"

echo "## Systemd User Units"
echo
echo "Linger enabled: $(loginctl show-user "$USER" 2>/dev/null | awk -F= '/^Linger/{print $2}')"
echo
echo "| Unit File | Description | State | Container(s) |"
echo "|-----------|-------------|-------|--------------|"

shopt -s nullglob
for f in "$HOME/.config/systemd/user/"*.service; do
  fname=$(basename "$f")
  desc=$(awk -F= '/^Description=/{print substr($0,index($0,"=")+1); exit}' "$f" | head -c 200)
  state=$(systemctl --user is-enabled "$fname" 2>/dev/null || echo "-")
  active=$(systemctl --user is-active "$fname" 2>/dev/null || echo "-")
  # Extract container names from ExecStart line
  containers=$(awk -F= '/^ExecStart=/{s=substr($0,index($0,"=")+1); gsub(/^-?\/usr\/bin\/podman[ \t]+(start|stop)[ \t]+/,"",s); print s; exit}' "$f" | tr -s ' ')
  printf '| %s | %s | %s/%s | %s |\n' \
    "$fname" "${desc:--}" "$state" "$active" "${containers:--}"
  cp -f "$f" "${host_dir}/systemd-units/$fname"
done
echo
echo "Copies of unit files: \`systemd-units/*.service\`"
echo
