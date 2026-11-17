# 同一台設備的 Apporo 並行入口

保留 WOOW 主入口，另加 Apporo Cockpit／PWA／Pi 入口，兩者共用**同一台主機的服務、備份引擎、Podman 應用與原生 Pi 資料**。新增一個前端容器與兩個 Pi gateway units，不建立第二組 47 個應用容器或租戶隔離。

兩品牌使用同一份[共同材料鎖](../brand-materials/2026.11.17-dual-brand.json)。目前材料尚待更新為最終已合併的 Cockpit commit／tree；舊 pin 缺少入口 installer 時，wrapper 會拒絕執行。歷史 rc1 的 lock、materials 與 tag 保持不變。

## 安裝前提

完整設定與低階 CLI 見 [Cockpit 並行入口說明](https://github.com/WOOWTECH/Woow_cockpit/blob/db4e38f/parallel-ingress/README.md)。目標是已有共同服務的設備：

- 使用固定且乾淨的 Cockpit source；已安裝 service helper、backup helper 與完整 backup engine 模組須和來源逐位元一致，差異會拒絕部署。
- 共同後端需更新時，先以同一來源的 `scripts/manage.py plan`／`install`／`verify` 同步；省略 `--brand`、`--service-owner` 保留原品牌與 owner 設定。新增入口不呼叫 distro 的 `brand` 或第二次 `apply`。
- 已由 `pi-web-integration/install.sh` 安裝 `woowpiweb` package，原生 Pi 正常運行且啟用獨立密碼；保留現有 LAN／VPN／public 設定。
- 原部署 owner 的 rootless Podman、systemd user manager 與 Quadlet 目錄已就緒。

## 設定 instance

依固定來源的 [config.example.json](https://github.com/WOOWTECH/Woow_cockpit/blob/db4e38f/parallel-ingress/config.example.json) 建立 `/etc/cockpit/parallel-ingress-config/apporo.json`。設定檔是 root-owned 一般檔案；檔案及所有祖先目錄不可經過 symlink、不可由 group／other 寫入。設定不含密碼、Token、Cookie 或 Cloudflare credentials。

| 欄位 | 範例／預設 |
| --- | --- |
| `schema`／`instance`／`brand` | `1`／`apporo`／`apporo` |
| `owner` | `operator`，替換為已有 rootless Podman owner |
| `public_origin` | `https://apporo.example.test`，替換為經核准的精確 HTTPS origin |
| `listen_port` | `29092`，只綁定 `127.0.0.1` |
| `compatibility_port` | `null`；只有需保留既有 public 轉送埠時才明確設定，例如 `18000` |
| `pi_public_port`／`pi_local_port` | `19096`／`19097`，均為 loopback gateways |
| `cockpit_port`／`pi_upstream_port` | `9090`／`30141`，須符合既有 backend |
| `node_path` | `/usr/bin/node` 或 `/usr/local/lib/woow-node/node` |
| `image` | 樣板中的固定 nginx registry digest；不使用浮動 tag 或 image config ID |

各個設定埠須互不重複。Node 與其祖先須符合 root ownership、非 symlink 及不可由 group／other 寫入的檢查。既有 instance 設定直接編輯，不以樣板覆寫。

## 安裝、驗證與回退

在可信的 distribution checkout，以原部署帳號執行 wrapper；由它準備來源並呼叫固定 Cockpit root CLI：

```bash
# 只讀來源選擇，不 fetch、不建立 state、不 sudo。
python3 distribution/installer/parallel-ingress.py plan

# 最終材料 pin 與 root-owned 設定就緒後執行。
python3 distribution/installer/parallel-ingress.py install \
  --config /etc/cockpit/parallel-ingress-config/apporo.json
python3 distribution/installer/parallel-ingress.py verify --instance apporo
python3 distribution/installer/parallel-ingress.py rollback --instance apporo
```

wrapper 的 `plan` 只報告 source selection，`instance_validated`／`runtime_verified` 為 false。需要先檢查 instance 與 backend parity 時，對已驗證來源使用 `sudo env PYTHONDONTWRITEBYTECODE=1 python3 <pinnedCockpit>/parallel-ingress/manage.py plan --config /etc/cockpit/parallel-ingress-config/apporo.json`。

install／verify／rollback 使用 `brand_profile.select()`／`prepare_source()`，核對已提交材料、完整 commit／tree、origin 與 main ancestry。來源放在 `~/.local/state/woow-release/2026.11.15-rc1/parallel-ingress/branding/production/<commit>/`，不改主要 `brand.json` receipt。config 驗證、交易與非零退出碼由 Cockpit CLI 負責；不接受未鎖定的開發來源。

root 產物位於 `/etc/cockpit/parallel-ingress/apporo/releases/`。沿用 `apporo-cockpit-pwa` Quadlet 名稱，配合獨立 public／local Pi units。rollback 只回退 journal 管理的入口／UI 設定與服務狀態，不還原應用資料、共同引擎、全域品牌、DNS 或 Access policy；偵測外部修改或不相容前版時拒絕覆寫。

## 本機與公開入口

本機預覽使用精確的 `http://127.0.0.1:29092`，不是 LAN／VPN listener。遠端可使用相同本機埠的 SSH 轉送，再以該 loopback URL 開啟；仍須登入 Cockpit 與 Pi：

```bash
ssh -N -L 127.0.0.1:29092:127.0.0.1:29092 operator@appliance.example.test
```

公開入口須由受信任的 Cloudflare HTTPS proxy 連到 loopback，保留正式 Host 與可信的 `X-Forwarded-Proto: https`。Cockpit Origins 以新增方式保留原 WOOW 來源，不偽造 browser Origin。可選 compatibility port 只接受正式 public 條件，不提供額外本機或 LAN 入口；installer 不修改 Cloudflare 路由、DNS、訂閱或 Access policy。

## 驗證範圍與待完成項目

詳細證據見 [2026-11-17 Cockpit 驗收紀錄](https://github.com/WOOWTECH/Woow_cockpit/blob/db4e38f/docs/parallel-ingress-validation-20261117.md)。已完成的結果如下：

| 範圍 | 結果 |
| --- | --- |
| 產物與後端 | 94 個受 receipt 管理的檔案、25 個共同後端檔案核對 |
| Apporo UI | 13 張應用卡片、311 項服務、49 個容器狀態與實際排程頁通過 |
| Pi 與品牌 | 真實助理回覆、SSE、手機尺寸與主題通過；原 WOOW HTTPS 入口的 Pi／主題回歸通過 |
| 入口生命週期 | 安裝 → 回退 → 前版 verify → 再安裝 → 新版 verify 通過 |
| 新 public origin 的本機可信 proxy 測試 | 登入 200、WebSocket 101、錯誤 Origin 403、匿名 401 |
| 自動測試 | Cockpit 32 項部署測試、distribution 60 項測試通過 |

服務／容器數是參考主機的查詢結果，不改 rc1 的 47-container profile。畫面參考的 17 個設備截圖位置明確顯示待擷取，不請求缺少的圖片；本次沒有重做正式應用資料的備份還原。

**新 Apporo 外網入口的 DNS／subscription 尚待核准與開通，外部 OTP／Access 未驗收。** 本機可信 proxy 的成功不代表新網域已上線；OTP 是獨立授權層，不會被此功能移除或繞過。範例網域不是可用入口。

Cockpit 最終 CI／合併結果與共同材料鎖中的完整 commit／tree 尚待確認。
