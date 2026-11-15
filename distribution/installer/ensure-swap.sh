#!/bin/bash
# A full reference stack needs headroom during first-run database migrations.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ -z $(swapon --show --noheadings) ]] || exit 0
path=/var/lib/woow-release/swapfile
install -d -m 700 /var/lib/woow-release
if [[ ! -e $path ]]; then
  case $(stat -f -c %T /var/lib/woow-release) in
    ext2/ext3|xfs) ;;
    *) echo 'Set up at least 4 GiB swap for this filesystem before continuing.' >&2; exit 1 ;;
  esac
  (umask 077; fallocate -l 4G "$path")
  chmod 600 "$path"
  mkswap "$path" >/dev/null
fi
[[ -f $path && ! -L $path && $(stat -c %u "$path") == 0 ]] || exit 1
swapon "$path"
grep -q '^/var/lib/woow-release/swapfile ' /etc/fstab ||
  printf '/var/lib/woow-release/swapfile none swap sw 0 0\n' >> /etc/fstab
