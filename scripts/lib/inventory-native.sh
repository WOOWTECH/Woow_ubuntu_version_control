#!/usr/bin/env bash
# inventory-native — record versions of native user toolchains.
set -euo pipefail

echo "## Native Toolchains"
echo
echo "| Tool | Version | Path |"
echo "|------|---------|------|"

check() {
  local label="$1"; local cmd="$2"
  local path=""; local ver="-"
  path=$(command -v "$cmd" 2>/dev/null || true)
  if [ -n "$path" ]; then
    ver=$("$cmd" --version 2>&1 | head -1 || echo "-")
  fi
  printf '| %s | %s | %s |\n' "$label" "${ver:--}" "${path:--}"
}

# NVM/Node — nvm is a shell function, need to source
NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
  nvm_ver=$(nvm --version 2>/dev/null || echo "-")
  node_default=$(nvm alias default 2>/dev/null | awk '{print $NF}' || echo "-")
  printf '| nvm | %s | %s |\n' "$nvm_ver" "$NVM_DIR"
  printf '| node (nvm default) | %s | - |\n' "$node_default"
fi

check node node
check pnpm pnpm
check corepack corepack
check rustup rustup
check cargo cargo
check python3 python3
check uv uv
check pipx pipx
check cloudflared cloudflared
check gh gh
echo

echo "### Installed Node versions (nvm)"
if [ -d "$NVM_DIR/versions/node" ]; then
  echo
  for v in "$NVM_DIR/versions/node"/*; do
    [ -d "$v" ] && echo "- $(basename "$v")"
  done
  echo
fi

echo "### Installed Rust toolchains (rustup)"
if command -v rustup >/dev/null 2>&1; then
  echo
  rustup toolchain list 2>/dev/null | sed 's/^/- /'
  echo
fi
