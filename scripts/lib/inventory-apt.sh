#!/usr/bin/env bash
# inventory-apt — print a markdown section listing manually-installed apt packages.
set -euo pipefail

echo "## APT Manual Packages"
echo
count=$(apt-mark showmanual 2>/dev/null | wc -l)
echo "Count: ${count}"
echo
echo "| Package | Installed | Latest (candidate) |"
echo "|---------|-----------|--------------------|"
apt-mark showmanual 2>/dev/null | sort | while read -r pkg; do
  cur=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || echo "-")
  cand=$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/{print $2; exit}' || echo "-")
  # Escape pipe chars in versions (rare but happens)
  cur=${cur//|/\\|}; cand=${cand//|/\\|}
  printf '| %s | %s | %s |\n' "$pkg" "$cur" "$cand"
done
echo
