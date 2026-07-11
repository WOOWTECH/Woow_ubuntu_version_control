#!/usr/bin/env bash
# inventory-repos — enumerate git repos under $HOME (max depth 3) and record
# their remote URL + current branch + commit hash.
set -uo pipefail

echo "## User Repos Cloned"
echo
echo "| Path | Remote | Branch | Commit |"
echo "|------|--------|--------|--------|"

# Search for .git dirs, ignore huge trees
find "$HOME" -maxdepth 4 -type d -name .git 2>/dev/null \
  -not -path "*/node_modules/*" \
  -not -path "*/.cargo/*" \
  -not -path "*/.rustup/*" \
  -not -path "*/target/*" \
  -not -path "*/.claude/*" \
  -not -path "*/.local/*" \
  -not -path "*/.cache/*" \
  -not -path "*/.nvm/*" \
  | sort | while read -r gitdir; do
    repo=$(dirname "$gitdir")
    rel="${repo#$HOME/}"
    remote=$(git -C "$repo" remote get-url origin 2>/dev/null); [ -z "$remote" ] && remote="-"
    if git -C "$repo" rev-parse --quiet --verify HEAD >/dev/null 2>&1; then
      branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null); [ -z "$branch" ] && branch="-"
      commit=$(git -C "$repo" rev-parse --short HEAD 2>/dev/null); [ -z "$commit" ] && commit="-"
    else
      branch="(no commits)"; commit="-"
    fi
    printf '| ~/%s | %s | %s | %s |\n' "$rel" "$remote" "$branch" "$commit"
  done
echo
