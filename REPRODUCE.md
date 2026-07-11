# REPRODUCE — 給 AI 讀的一頁復現指南

**目標讀者：** Claude Code（或任何 AI agent）在一台**空的 Ubuntu 22.04 / 24.04** 上
把本 repo 記錄的某台主機狀態 1:1 復刻出來。

**期望產出：** 全部 podman 服務跑起來，cockpit 可連，`scripts/verify.sh` 全綠。

---

## Step 0 — 決定要復現哪一台

`ls -d */` 列出所有 host folder。挑一個作為 `HOST`（例如 `1-N100-toypark1234`）。

```bash
export HOST=1-N100-toypark1234
```

---

## Step 1 — 底座：跑 `ubuntu-skills/podman-host-bootstrap`

本 repo **不重複造輪子**。裝 podman + cockpit + linger + subuid/gid 這些通用步驟
交給姊妹 repo：

```bash
[ -d ~/ubuntu-skills ] || git clone https://github.com/toypark1234/ubuntu-skills ~/ubuntu-skills
bash ~/ubuntu-skills/podman-host-bootstrap/verify.sh || \
  echo "→ 先跑 ubuntu-skills/podman-host-bootstrap/SKILL.md 的 Step 1–5 再回來"
```

（該 skill 的 SKILL.md 是 Claude Code 讀的指令集；如果你是純腳本，見裡面的 apt
install / linger / socket 命令。）

---

## Step 2 — 取得 backup tar

Backup **不在 git 裡**。從 `$HOST/snapshot-manifest.md` 讀 sha256 + 檔名 + 原始路徑，
然後把 tar 拿過來：

```bash
cat $HOST/snapshot-manifest.md
```

複製到目標機：

- 若使用者已把 tar 放到 `/tmp/backup-$HOST.tar.zst` → 直接進 Step 3。
- 否則 scp / rsync 從源機拉過來。若沒有 tar → **停下來問使用者**。

驗證 sha256：
```bash
want=$(awk -F'|' '/^\| sha256 \|/{gsub(/ /,"",$3); print $3; exit}' $HOST/snapshot-manifest.md)
have=$(sha256sum /tmp/backup-$HOST.tar.zst | awk '{print $1}')
[ "$want" = "$have" ] && echo "OK" || { echo "sha256 mismatch"; exit 1; }
```

---

## Step 3 — 收集 external secrets

看看哪些需要人工提供：
```bash
bash scripts/list-secrets.sh $HOST
```

典型清單：`ANTHROPIC_API_KEY` / `MINIMAX_API_KEY` / `HOMEASSISTANT_TOKEN` /
`CF_API_TOKEN` / `CF_ACCOUNT_ID` / `CF_ZONE` / Claude OAuth JSON / VK admin creds。

存到 `~/.homelab/secrets.env`（mode 600）— 一行一 `KEY=value`。復原腳本會 source。

---

## Step 4 — 執行 restore

```bash
bash scripts/restore.sh $HOST
```

腳本會：
1. Preflight（`podman`, `podman-compose`, `zstd` etc.）
2. 校驗 `/tmp/backup-$HOST.tar.zst` sha256
3. 解開 tar，把 `~/.config/systemd/user/`、`~/.cloudflared/`、`~/ha-config/`、
   `~/matter-server-data/`、各服務 `.env` 復原
4. 從 install-list.md 抓出所有 cloned repos 的 remote URL，`git clone` 回來
5. 匯入 podman volumes（來自 tar 內 `podman-volumes/*.tar`）
6. 按順序 `podman-compose up -d`（cf-tunnel → webgui → immich → n8n → ha-mcp → hermes → vibe-kanban）
7. `systemctl --user enable --now` 全部 unit

---

## Step 5 — Verify

```bash
bash scripts/verify.sh $HOST
```

全綠 = 復現成功。若有 fail：
- 看 `podman ps -a` 確認容器狀態
- 看 `journalctl --user -u podman-<name>.service` 找錯
- 若 Postgres 空 → 檢查 tar 內 `pgdumps/`；restore 目前**只還原 volume 資料**，
  若 volume 是空的可以手動 `zcat pgdumps/foo.sql.gz | podman exec -i <container> psql -U <user>`

---

## Step 6 — 收尾

- `git status` 確認本 repo 沒被動到
- 開 Cockpit：`https://<host-ip>:9090/`
- Cloudflare tunnel 已用回同一個 tunnel ID（backup 內含 credentials JSON），故 DNS
  routes 不需重建。若是全新 tunnel → 見 `~/ubuntu-skills/homelab-deploy/services/cf-tunnel.md`

---

## 對 AI 的補充規則

1. **不要跳步。** 每步都印 `[ok]` / `[fail]`。fail 停下來問人，不要嘗試「fix and continue」。
2. **不要重跑 capture.sh。** capture 會覆寫 host folder 內容 — 只在源機、要記錄新
   狀態時執行。
3. **不要把 `~/.backups/*.tar.zst` 或 `.env` 加進 git。** `.gitignore` 已擋，但如果你
   看到 `git status` 出現這類檔案，先停下確認。
4. **PAT / API key / OAuth JSON** 一律用 `scripts/list-secrets.sh` 蒐集後放在 `~/.homelab/`，
   不寫進本 repo 任何檔案。
