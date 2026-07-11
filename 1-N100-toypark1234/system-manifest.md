# System Manifest — 1-N100-toypark1234

## Host Identity

| Key | Value |
|-----|-------|
| hostname | toypark1234-Default-string |
| static hostname | toypark1234-Default-string |
| machine-id | 9df0df2a758647828917d3a71f4239bf |
| CPU | Intel(R) N100 |
| Cores | 4 |
| RAM | 15Gi |
| Disk / | 233G total, 76G used, 146G avail |
| OS | Ubuntu 24.04.4 LTS |
| Kernel | 6.17.0-20-generic |
| Architecture | x86_64 |
| Linger | yes |

## Compose Files (source of truth)

| Service | Path | Copied to |
|---------|------|-----------|
| hermes_deploy_hermes_podman | ~/hermes_deploy/hermes/podman/podman-compose.yml | compose/hermes_deploy_hermes_podman.yml |
| podman_hermes | ~/podman/hermes/docker-compose.yml | compose/podman_hermes.yml |
| projects_open-design_deploy | ~/projects/open-design/deploy/docker-compose.yml | compose/projects_open-design_deploy.yml |
| vibe-kanban-stack | ~/vibe-kanban-stack/docker-compose.yml | compose/vibe-kanban-stack.yml |
| Woow_cloudflare_tunnel_webgui | ~/Woow_cloudflare_tunnel_webgui/docker-compose.yml | compose/Woow_cloudflare_tunnel_webgui.yml |
| Woow_ha_ai_mcp | ~/Woow_ha_ai_mcp/docker-compose.yml | compose/Woow_ha_ai_mcp.yml |
| Woow_immich_docker_compose_all | ~/Woow_immich_docker_compose_all/docker-compose.yml | compose/Woow_immich_docker_compose_all.yml |
| Woow_n8n_docker_compose_all | ~/Woow_n8n_docker_compose_all/docker-compose.yml | compose/Woow_n8n_docker_compose_all.yml |

## External Secrets Required

These must be provided when restoring on a new host. `scripts/list-secrets.sh` prints
the same list interactively.

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

## Ports Exposed (host bindings)

| Port | Process/Container |
|------|-------------------|
| 22 | - |
| 53 | - |
| 631 | - |
| 2019 | (("caddy",pid=3816860,fd=4)) |
| 2283 | (("rootlessport",pid=3324960,fd=5)) |
| 3000 | (("vibe-kanban",pid=614668,fd=14)) |
| 5580 | (("rootlessport",pid=12436,fd=11)) |
| 7456 | (("caddy",pid=3816860,fd=7)) |
| 7457 | (("MainThread",pid=3830934,fd=25)) |
| 8000 | (("uvicorn",pid=2976889,fd=11)) |
| 8081 | (("rootlessport",pid=3703397,fd=11)) |
| 8082 | (("rootlessport",pid=3703756,fd=10)) |
| 8123 | (("python3",pid=1582037,fd=14)) |
| 8888 | (("rootlessport",pid=3787703,fd=11)) |
| 9090 | - |
| 9333 | (("chrome",pid=953465,fd=79)) |
| 15678 | (("rootlessport",pid=13933,fd=11)) |
| 18554 | (("go2rtc",pid=1582601,fd=6)) |
| 18555 | (("go2rtc",pid=1582601,fd=7)) |
| 18642 | (("rootlessport",pid=563787,fd=10)) |
| 18787 | (("rootlessport",pid=564035,fd=5)) |
| 19119 | (("rootlessport",pid=563787,fd=12)) |
| 20241 | (("cloudflared",pid=2976934,fd=10)) |
| 21064 | (("python3",pid=1582037,fd=78)) |
| 35569 | (("claude",pid=3336913,fd=18)) |
| 39441 | (("claude",pid=3336378,fd=18)) |
| 41433 | (("claude",pid=3337579,fd=18)) |
| 44471 | (("vibe-kanban",pid=614668,fd=15)) |

