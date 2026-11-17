# 雙品牌 Cockpit 材料鎖

新版 main 採用 **base_rc1 + common brand layer**。woowtech／apporo 共用同一個整機引擎、硬體方案、47 個容器、映像內容鎖、服務 ID、資料路徑及 Secret 名稱，兩份品牌 profile 必須預設同一個新 Cockpit 材料鎖／commit／tree。woowtech 仍是首次安裝預設品牌；兩品牌使用相同 UI engine 與功能提交。此目錄不取代或修改歷史 rc1 的 lock/materials/tag；精確重現舊版請在獨立 checkout 使用 `v2026.11.15-rc1` 及該版文件。

兩份 profile 已共同預設 [2026.11.17-dual-brand.json](2026.11.17-dual-brand.json)。Cockpit 功能來源為 `73871247139a054de07c2e4275a6108aa2cd5bb0`，包含 [PR16 排程備份](https://github.com/WOOWTECH/Woow_cockpit/pull/16) 與 [PR17 雙品牌](https://github.com/WOOWTECH/Woow_cockpit/pull/17)，兩品牌使用同一 renderer、素材介面、備份引擎、PWA 與 Pi gateway。預設 WOOW 與 Apporo 的 plan 都選擇 production 來源。

可選的[Apporo 並行入口](../docs/parallel-brand-ingress.md)另有獨立 wrapper 與 staging，不更新主要 `brand.json`。目前等待包含該功能的最終 Cockpit pin；本材料鎖仍是上述來源，不代表並行入口已可正式安裝。

## 介面

```bash
# 純讀取計畫，不建立設備 state、不呼叫 sudo/Podman。
python3 distribution/installer/woow-release.py plan
python3 distribution/installer/woow-release.py plan --brand apporo

# 正式品牌切換：只在已由本 distribution 管理的隔離驗收設備執行。
python3 distribution/installer/woow-release.py brand --brand apporo

# 開發：來源須已 commit 且工作樹乾淨；不要求已合併上游 main。
python3 distribution/installer/woow-release.py plan --brand apporo \
  --development --cockpit-source /path/to/clean-cockpit-checkout

# 僅在獨立驗收設備執行：已由這份 distribution 管理的完整設備。
python3 distribution/installer/woow-release.py brand --brand apporo \
  --development --cockpit-source /path/to/clean-cockpit-checkout
```

`brand` 會安裝 Cockpit 呈現與 PWA，Pi 僅更新 gateway.mjs、index.html、style.css，保留 app.js、manifest、所有 gateway units 與網路設定；僅重啟原本 active 的 LAN／VPN／public Pi gateway，然後執行原有完整 runtime `verify`。它不重跑應用安裝、帳號 bootstrap、Secret 生成，也不重設現有 `cockpit.conf` 或 service owners。它不是任意既有主機的升級工具。`--development` 只適用 `plan` 與 `brand`，不能搭配完整 `apply` 或繞過正式 `verify`。

來源複製到 `~/.local/state/woow-release/2026.11.15-rc1/branding/<mode>/<commit>/`，不修改提供來源的 checkout，也不覆寫歷史 `sources/Woow_cockpit`。省略 `--brand` 時使用已有 receipt 的品牌，否則是 woowtech。已有開發 receipt 時，重新套用須再次明確提供開發來源或正式材料鎖。

## 正式 pin

已提交的共同材料鎖內容如下：

```json
{
  "schema_version": 1,
  "base_release": "2026.11.15-rc1",
  "base_lock_sha256": "2cf7665543b030371f58ccce0f0706cc031f9b2015925f153e10452d223b05de",
  "brands": ["woowtech", "apporo"],
  "cockpit": {
    "repository": "https://github.com/WOOWTECH/Woow_cockpit.git",
    "commit": "73871247139a054de07c2e4275a6108aa2cd5bb0",
    "tree": "d85fb2ca56c8d14f602ff80da8ba3e58d8d1fbbb",
    "main_commit": "73871247139a054de07c2e4275a6108aa2cd5bb0",
    "interface_version": 1
  }
}
```

同一份鎖必須支援兩品牌；Git tree 同時釘選程式與素材。安裝器檢查：基底鎖一致、JSON 未偏離本倉庫 HEAD 的已提交內容、來源 repository 固定、完整 commit/tree 一致，且來源 commit 是已釘選 main commit 的祖先，後者仍在取得的上游 `origin/main` 中。未合併 PR 可以使用明確開發模式驗證，不能藉手寫 lock 變成正式材料。

PR17 CI 的合併測試 commit `f871421da0fb391a61eae46794feb5fd2bd487ee` 與上述 main commit 的 tree 完全相同，已由 GitHub commit API 核對。主代理提供的該輪結果為 1056 項 Python 測試、每品牌 79 項備份 UI，以及兩品牌 PWA／服務／Pi 測試通過；另外以整合來源完成隔離 apporo → woowtech → apporo 切換，涵蓋新增 timer units 落檔與 manage verify。這些證據涵蓋合併後的排程功能；後續 docs-only PR18 不改本功能 pin。

```bash
sha256sum distribution/releases/2026.11.15-rc1/lock.json
git -C /path/to/cockpit rev-parse HEAD 'HEAD^{tree}'

# 兩品牌 profile 已設定共同預設；亦可明確指定同一份鎖。
python3 distribution/installer/woow-release.py plan --brand apporo \
  --brand-lock distribution/brand-materials/2026.11.17-dual-brand.json
python3 distribution/installer/woow-release.py apply --brand apporo \
  --brand-lock distribution/brand-materials/2026.11.17-dual-brand.json \
  --materials /path/to/authorized-materials/images --address <LAN-IPv4>
```

`distribution/brands/{woowtech,apporo}.json` 的 `material_lock` **同時設為同一檔名**，後續更新也必須保持一致；不能讓新版 woowtech 留在舊 Cockpit、apporo 使用新 Cockpit。這是 rc1 基底加共同品牌層，不能宣稱歷史 `v2026.11.15-rc1` 已包含 Apporo 或沿用其驗收結論。`plan` 的 ready 表示本地材料選擇有效，實際上游來源 provenance 在安裝前檢查；計畫不是 runtime 驗收證據。

## 排程與來源 overlays 相容性

這份來源包含共同的備份排程功能，並非只有 CSS／標誌變更。`brand` 呼叫完整 Cockpit installer，會安裝固定的 `woowtech-cockpit-backup-schedule.timer`／`.service`，沿用 PR16 的語義：未 masked 的 timer 若 disabled 或 inactive，會 `enable --now`；已有 active timer 在備份套件檔案更新期間暫停，完成後恢復。即使檔案已是最新版，重跑仍會啟用被停用的 timer；masked 狀態保留。不可把切品牌描述成保留 disabled／stopped timer 狀態。

installer 不覆寫既有 `schedule.json`、`retention.json`、排程 state、archives 或 keys；沒有 schedule 設定時預設關閉排程備份。既有啟用排程會由 timer 繼續檢查並依設定執行。timer 狀態已用固定來源函式與記憶體 runner 重現，未操作主機服務。這次不新增備份引擎 overlay，也不更改兩品牌的排程行為。

四項既有 overlays 仍相容：held-package 判斷與備份 tools/order 41 已在上游，兩個補丁會直接返回；Pi 的 `/usr/bin/node` 路徑仍可替換成 distribution 的 root-owned Node；PWA 的唯一 Image 與固定 ContainerName 仍可鎖定原 rc1 image ID／`Pull=never`。既有資料路徑、服務 ID、Secrets 和容器映像鎖未因品牌改名。

## 品牌切回與回退範圍

已套用雙品牌的設備，使用同一份 production pin 協調切回 WOOW：

```bash
python3 distribution/installer/woow-release.py brand --brand woowtech \
  --brand-lock distribution/brand-materials/2026.11.17-dual-brand.json
```

這會同步 Cockpit、PWA 與 Pi 呈現並重新驗證，保留應用資料與網路設定，timer 依上述 installer 語義處理。Cockpit `scripts/manage.py rollback` 還原其 journal 管理的檔案（包含 brand.json）及該交易涵蓋的 timer 狀態；它不會回復 PWA 產物或重啟已載入舊配色的 Pi gateway。單獨使用該低階回退後，仍須依回復品牌 refresh PWA，並重啟既有 active gateways；完整品牌切回請使用上述 distribution 動作。

## Receipt 與驗證

`brand.json` 位於原有 release state，記錄品牌、development/production、base lock SHA、材料鎖 SHA、來源 commit/tree、已審查 source overlays 與 installing/applied 狀態；不記錄任何帳密。來源 overlays 限既有兩項 Cockpit 相容補丁、Pi 的 root-owned Node 路徑，以及 PWA Quadlet 的**同一個 rc1 image ID／Pull=never**。來源漂移會拒絕續跑或驗證，不自動刪除 stage 掩蓋異常。

`verify` 保留原先容器 image IDs、健康、原生 CLI、套件、服務與 HTTP 檢查，另外檢查：

- receipt 與材料鎖／來源 commit/tree／來源 overlays 一致。
- Cockpit 的 managed-file journal 通過，安裝的 `brand.json` ID 正確。
- 安裝的 Pi gateway 程式／靜態頁面與受鎖定來源相符。
- PWA Quadlet 與固定映像相符；用同一個固定 renderer 產生的 manifest、圖示、nginx 設定與已安裝檔案逐項一致。

開發模式報告保留 `runtime_passed`，但 `release_eligible: false`、`passed: false`。開發 `brand` 動作僅在 runtime 檢查通過時退出 0；一般 `verify` 仍退出非零，避免把開發檢查當成正式交付。正式模式的任一原有 runtime 或新增品牌檢查失敗都不能通過。

素材與 browser matrix 由 Cockpit/PWA/Pi 分工驗證；本 distribution 的測試不代替隔離 VM 安裝、重啟、實際備份還原與跨品牌 UI 驗收。

測試把未配置／legacy 情境放在獨立 fixture 或 profile mock；正式 plan 允許唯讀 `git show HEAD:distribution/brand-materials/...` 檢查已提交材料，禁止安裝與網路命令。兩品牌的預設 plan 必須選到同一材料鎖與來源 commit/tree。
