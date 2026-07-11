#!/usr/bin/env bash
# inventory-cloudflared — list tunnel routes from ~/.cloudflared/config.yml
# and copy the config (routes only, credentials excluded) to host folder.
set -uo pipefail
host_dir="$1"
mkdir -p "${host_dir}/cloudflared-config"

echo "## Cloudflared Tunnel Routes"
echo
cfg="$HOME/.cloudflared/config.yml"
if [ ! -f "$cfg" ]; then
  echo "(no ~/.cloudflared/config.yml found)"
  echo
  exit 0
fi

# Copy config (safe — it only points at credentials-file, doesn't include the JSON itself)
cp -f "$cfg" "${host_dir}/cloudflared-config/config.yml"

echo "| Hostname | Service |"
echo "|----------|---------|"
python3 - "$cfg" <<'PY' 2>/dev/null || true
import sys, re
with open(sys.argv[1]) as f:
    src = f.read()
# Cheap parser: look for hostname: / service: pairs
pairs = re.findall(r'-\s*hostname:\s*(\S+)\s*\n\s*service:\s*(\S+)', src)
for h, s in pairs:
    print(f"| {h} | {s} |")
if not pairs:
    print("| (no `hostname:` blocks parsed) | - |")
PY

echo
echo "Tunnel names configured:"
if command -v cloudflared >/dev/null 2>&1; then
  cloudflared tunnel list 2>/dev/null | tail -n +2 | awk '{printf "- %s (%s)\n", $2, $1}' || true
fi
echo
echo "Config file copy: \`cloudflared-config/config.yml\`"
echo "Credentials JSON (\`~/.cloudflared/<tunnel-id>.json\`) is sensitive — NOT copied here; included only in the encrypted backup tar."
echo
