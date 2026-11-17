# WOOW Ubuntu Version Control

以固定版本在新設備建立 Ubuntu 24.04 x86_64、rootless Podman／Quadlet、WOOW Cockpit、原生 Pi 與應用服務。來源為 woowtechopenclaw 的正式組合；不複製原設備的帳號、檔案、資料庫或雲端登入。

- [新設備安裝與材料取得](distribution/README.md)
- [架構、版本與設備邊界](distribution/docs/architecture.md)
- [安裝後驗收、備份及還原流程](distribution/docs/acceptance.md)
- [x86_64 預裝方案](distribution/profiles/openclaw-x86_64.json)
- [2026.11.15-rc1 來源與映像版本鎖](distribution/releases/2026.11.15-rc1/lock.json)
- [第二台 N100 的新機建置實測與限制](distribution/releases/2026.11.15-rc1/VALIDATION.md)
- [既有設備保留資料升級](distribution/docs/existing-device-upgrades.md)
- [既有實體設備重開機驗收](distribution/docs/reboot-acceptance.md)
- [woowtech／apporo 共用引擎、品牌計畫與材料鎖](distribution/brand-materials/README.md)（WOOW 預設保留；Apporo 正式來源 pin 待完成）

本候選版包含 15 個來源提交、37 個映像與 47 個正式容器，另有原生 Pi Web 及三代理 CLI。HA 品牌映像、Odoo 等二進位安裝材料透過 WOOW 授權管道交付；公開 Git 倉庫提供程式、校驗碼、設定及說明。請指定交付的 release tag／commit，依同版驗收紀錄判讀支援範圍。

`distribution/` 是全新建置流程。根目錄的 `scripts/capture.sh`、`scripts/restore.sh` 及既有主機資料夾屬於較早的私人備份還原流程；新設備安裝請勿混用。

<details>
<summary>歷史主機快照與舊版 capture／restore 文件</summary>

**姊妹專案：** `WOOWTECH/Woow_ha_version_control` 針對 Home Assistant OS；本專案針對
一般 Ubuntu Server（跑 podman + cockpit 的 homelab 底座）。

## 主機列表

| 編號 | 資料夾 | 硬體 |
|------|--------|------|
| U1 | `1-N100-toypark1234/` | Intel N100 mini PC |

（新增主機時附上一列。）

## 資料夾結構

每一台主機對應一個資料夾：

```
{編號}-{硬體代稱}-{host}/
  install-list.md         # 該版本安裝的所有資源清單（apt、podman、systemd unit、native toolchains、cloned repos、cloudflared routes）
  system-manifest.md      # 主機 identity、compose 檔位置、需要的 external secrets、對外 port 表
  wish-list.md            # 計畫但尚未實作的服務
  snapshot-manifest.md    # 最新 backup tar 的 sha256 / 大小 / 存放位置
  compose/                # 各服務 docker-compose.yml 的脫敏副本
  systemd-units/          # ~/.config/systemd/user/*.service 副本
  cloudflared-config/     # ~/.cloudflared/config.yml（ingress 路由，不含 credentials JSON）
```

- **install-list.md** 記錄該版本實際安裝的所有資源，含版本、來源 repo URL、掛載點。
- **system-manifest.md** 是 AI 讀來復現時的主要指南 — 主機硬體 fingerprint、每個服務
  compose 檔位置、必要 external secrets 清單（值不在裡面，只有名稱＋取得方式）。
- **snapshot-manifest.md** 記錄最新 backup tar 的 sha256 與存放位置；tar 本身**不進 git**
  （敏感資料），得由使用者自行搬運到目標機。
- **wish-list.md** 由人手動維護。

## 版本控制方式

**一個 commit 代表一個系統狀態版本。**

每次對任一台主機做變更（裝新服務、升級、config 調整），跑 `scripts/capture.sh` 重新
掃描一次，把新產出的 markdown/config 一併 commit。透過 `git log --oneline` 即可看出
「這台機在什麼時間點裝了什麼」，也能 `git checkout <commit>` 回到任一版本的清單。

## 敏感資料策略

**backup tar 永不 push 到 GitHub。** 只有純文字 markdown / config 進 git。

|類別 | 進 git | 進 tar |
|---|---|---|
| markdown / scripts / compose 結構 | ✅ | — |
| systemd unit file 內容 | ✅ | ✅ |
| cloudflared `config.yml`（routes） | ✅ | ✅ |
| cloudflared credentials JSON | ❌ | ✅ |
| 各服務 `.env` | ❌ | ✅ |
| `.claude-oauth.env` | ❌ | ✅ |
| ha-config 全目錄（含 secrets.yaml） | ❌ | ✅ |
| Postgres dumps | ❌ | ✅ |
| Immich library / Postgres 大檔 | ❌ | ⚠️ 依大小可選 |
| Podman images | ❌ | ❌（restore 時 pull） |
| 各上游程式碼 repo | ❌ | ❌（restore 時 clone） |

Backup tar 落在 `~/.backups/`（可透過 `BACKUP_DEST` 覆寫）。複製到目標機時走
SCP／NAS／USB — 你自己決定信任邊界。

## 復現流程（給 AI／新機）

看 [`REPRODUCE.md`](REPRODUCE.md)。一頁完整走完：底座 → 拉 backup → 展開 → 起服務 →
驗證。

## 上游 recipe submodules

以下 submodule 是**跨機共用的部署 recipe**，釘在該產品目前為 hybrid host + podman
架構的分支上。任一台 Ubuntu 主機的 `system-manifest.md` 都可指向這些 recipe。

| Path | Upstream | Branch |
|------|----------|--------|
| `opendesign/` | `WOOWTECH/Woow_opendesign_docker_compose_all` | `podman` |
| `vibe-kanban/` | `WOOWTECH/Woow_vibekanban_docker_compose_all` | `podman-ubuntu` |

Hermes recipe 位置預留 TODO — 目前 upstream `podman` 分支的 hybrid 設計前提尚未確認
（image 是第三方 `docker.io/nousresearch/hermes-agent`，非 Node CLI），確認前不加。

拉取或更新:
```bash
git submodule update --init --recursive
git submodule update --remote opendesign vibe-kanban
```

## 姊妹 skill：`ubuntu-skills`

本 repo **只記錄「這台機的狀態」**。**「怎麼把 Ubuntu 裝成能跑 podman + cockpit 的
homelab 底座」** 由另一個 repo `ubuntu-skills` 負責，內含兩個 Claude Code skill：
`podman-host-bootstrap` + `homelab-deploy`。`REPRODUCE.md` 會告訴 AI 何時該去呼叫。

## 腳本

| 腳本 | 用途 |
|------|------|
| `scripts/capture.sh <host>` | 掃描當前機器，產出 `<host>/*.md` + copy compose + 產生 backup tar 到 `~/.backups/` |
| `scripts/restore.sh <host>` | 從 `<host>/` folder + 一份 backup tar 復原到當前機器 |
| `scripts/verify.sh <host>` | 復原後 L2 HTTP smoke test 全部服務 |
| `scripts/list-secrets.sh <host>` | 列出該 host 復原需要的 external secrets |

## 誰在讀這個 repo

**AI**（例如 Claude Code）：從 `REPRODUCE.md` 開始，一步步呼叫 `scripts/`。

**人**：從 `install-list.md`／`git log` 快速理解某台機當前跑什麼、跟半年前差在哪。

</details>
