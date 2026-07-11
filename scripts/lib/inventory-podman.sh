#!/usr/bin/env bash
# inventory-podman — dump podman images, containers, volumes, networks as markdown.
set -euo pipefail

echo "## Podman Images"
echo
echo "| Repository | Tag | Size | Digest |"
echo "|------------|-----|------|--------|"
podman images --format '{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.Digest}}' 2>/dev/null \
  | sort | while IFS=$'\t' read -r repo tag size digest; do
      printf '| %s | %s | %s | %s |\n' "$repo" "$tag" "$size" "$digest"
    done
echo

echo "## Podman Containers"
echo
echo "| Name | Image | Ports | Restart | Networks | State |"
echo "|------|-------|-------|---------|----------|-------|"
podman ps -a --format '{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Networks}}\t{{.Status}}' 2>/dev/null \
  | sort | while IFS=$'\t' read -r name image ports networks status; do
      restart=$(podman inspect "$name" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo "-")
      printf '| %s | %s | %s | %s | %s | %s |\n' \
        "$name" "$image" "${ports:--}" "$restart" "${networks:--}" "$status"
    done
echo

echo "### Container Volume Mounts"
echo
echo "| Container | Source → Dest | RW |"
echo "|-----------|---------------|----|"
podman ps -a --format '{{.Names}}' 2>/dev/null | sort | while read -r name; do
  podman inspect "$name" --format \
    '{{range .Mounts}}| '"$name"' | {{.Source}} → {{.Destination}} | {{if .RW}}rw{{else}}ro{{end}} |
{{end}}' 2>/dev/null
done
echo

echo "## Podman Volumes"
echo
echo "| Name | Driver | Mountpoint |"
echo "|------|--------|------------|"
podman volume ls --format '{{.Name}}\t{{.Driver}}\t{{.Mountpoint}}' 2>/dev/null \
  | sort | while IFS=$'\t' read -r n d m; do
      printf '| %s | %s | %s |\n' "$n" "$d" "$m"
    done
echo

echo "## Podman Networks"
echo
echo "| Name | Driver | Subnet |"
echo "|------|--------|--------|"
podman network ls --format '{{.Name}}\t{{.Driver}}' 2>/dev/null | sort \
  | while IFS=$'\t' read -r n d; do
      subnet=$(podman network inspect "$n" --format '{{range .Subnets}}{{.Subnet}} {{end}}' 2>/dev/null || echo "-")
      printf '| %s | %s | %s |\n' "$n" "$d" "${subnet:--}"
    done
echo
