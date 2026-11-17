# 同一台設備的 Apporo 並行入口

這是既有主機的可選第二個管理入口。WOOW 與 Apporo 連到**同一份 Cockpit、Podman 應用、備份引擎及原生 Pi**；新增的是入口與品牌呈現。它不建立第二組 47 個應用容器，也不提供租戶隔離。從任一入口執行的服務、備份或 Pi 操作，都作用於同一台設備及相同資料。

目前為整合草稿：本 distribution 的共同材料仍釘在 `73871247139a054de07c2e4275a6108aa2cd5bb0`，尚未更新為包含 `parallel-ingress/manage.py` 的最終 Cockpit 提交。下列介面已與 Cockpit 主代理確認；正式安裝須等共同材料鎖更新、來源驗證及 Cockpit 驗收完成。現有 pin 缺少該入口時，wrapper 會在呼叫 sudo 前拒絕。文件與單元測試不代表已在實體主機部署。

## 選擇正確的流程

| 需求 | 流程 | 影響範圍 |
| --- | --- | --- |
| 全新設備建立整套服務 | `woow-release.py apply --brand apporo` | 新設備的完整應用與全域品牌 |
| 已由 distribution 管理的設備切換全域品牌 | `woow-release.py brand --brand apporo` | 現有主要 Cockpit／PWA／Pi 呈現 |
| 保留 WOOW，另加 Apporo 管理入口 | 本頁的 `parallel-ingress.py` | 個別 instance 的入口；共用原主機後端 |

並行入口不呼叫 `brand`、`cockpit` 或 `apply`。其來源與主要品牌使用同一份已審查材料；全域 `brand.json` receipt 及品牌選擇仍由原安裝流程管理。

```mermaid
flowchart LR
  W[既有 WOOW 入口] --> C[同一個 Cockpit backend]
  A[Apporo HTTPS / PWA 入口] --> C
  C --> S[既有 Podman 服務與備份引擎]
  A --> G[Apporo 的兩個 Pi gateway units]
  G --> P[同一個原生 Pi upstream]
```

## Config 與主機責任

Cockpit root installer 接受 root 擁有的 JSON，schema 為 1。設定不包含密碼、Token、Cookie、Linux 登入或 Podman secrets；既有帳號、服務擁有者及授權繼續使用。以最終固定來源中的 schema／範例及 `plan` 驗證設定，wrapper 不複製另一套 config validator。

| 欄位／用途 | 此次介面約定 | 說明 |
| --- | --- | --- |
| `schema` | `1` | 已對照目前 Cockpit renderer；正式使用前仍核對最終固定來源 |
| `instance` | `apporo` | instance 的生命週期識別 |
| `brand` | `apporo` | 此入口的呈現，不改全域品牌 |
| `owner` | `woowtechopenclaw` | 範例主機原有的 rootless Podman owner；新主機須依現況填寫 |
| `public_origin` | `https://apporo.example.test` | 該設備已配置的 HTTPS origin；範例網域不可直接用於正式入口 |
| `listen_port` | `29092` | 此 instance 的主要入口埠 |
| `compatibility_port` | `18000`，可省略 | public 相容別名；不是第二份應用，也不應作為 LAN／VPN 的廣泛別名 |
| `pi_public_port` | `19096` | 此 instance 的 public Pi gateway |
| `pi_local_port` | `19097` | 此 instance 的 local Pi gateway |
| `cockpit_port` | `9090` | 已有 Cockpit backend；若設備已移到其他埠，須填實際 backend 埠 |
| `pi_upstream_port` | `30141` | 同一個原生 Pi upstream |
| `node_path` | `/usr/bin/node` | root installer 驗證的 Node 路徑；不使用可由一般帳號修改的執行檔 |
| `image` | 固定 nginx digest | 使用已核對的 immutable image reference；不使用浮動 tag |

上表是介面交接，不是可直接安裝的 JSON。這份 rc1 鎖的 PWA nginx 來源 reference 是 `docker.io/nginxinc/nginx-unprivileged@sha256:5aea7cc516b419e3526f47dd1531be31a56a046cfe44754d94f9383e13e2ee99`；image config ID 是 `sha256:696695300a3c18a324c07ecb41f220e8c470302148b0378770cf5c70e6458ea0`。兩者不同，不能互換。最終入口 config 的映像仍須符合 Cockpit installer 支援的格式與已審查材料，不藉此改寫 rc1 的既有 PWA image alias。

設定與產物由 Cockpit root installer 管理，root 檔案放在 `/etc/cockpit/parallel-ingress/<instance>/releases/...`。Apporo 使用者 Quadlet 沿用 `apporo-cockpit-pwa` 名稱，以支援既有樣板入口的原地更新；兩個 Pi gateway 是分開的 root systemd units。精確檔案清單、unit 名稱及 transaction journal 以最終來源的 plan／verify 為準。

安裝前，Cockpit installer 嚴格比對主機已安裝的管理 helper／engine bytes 與固定來源；不一致時拒絕部署。不能靠這個 wrapper 順帶升級共享後端，也不能為繞過 parity 檢查而全域切成 Apporo。共享後端同步應另按 Cockpit 的維護流程處理並保留主入口品牌。

Cockpit `Origins` 以新增允許 origin 的方式處理，保留原 WOOW origin；proxy 不偽造 `Origin` 來繞過驗證。現有主機的 Cloudflare／DNS／TLS／Access 設定須維持有效；新增 JSON 不代表外網路由已完成。

## Distribution wrapper

以原部署帳號在受信任的 distribution checkout 操作。wrapper 不接受開發來源或任意 material lock，固定使用兩品牌共同的 production 材料。

```bash
# 只讀取本機已提交材料，不建立 state、不 fetch、不 sudo。
python3 distribution/installer/parallel-ingress.py plan
```

這個 `plan` 僅輸出來源選擇，明確標示 `scope: source-selection`、`instance_validated: false` 及 `runtime_verified: false`。其中 source 的 ready／release_eligible 沿用材料選擇語義，不代表 parallel CLI 存在、instance 設定有效、backend parity 通過或主機已完成驗收。它不解析 Cockpit `plan` 的 JSON，避免上游 metadata 尚未定稿時建立錯誤依賴。

正式來源與 instance config 就緒後，wrapper 的介面如下；這些是設備操作指令，本次文件與測試工作沒有執行它們：

```bash
python3 distribution/installer/parallel-ingress.py install \
  --config /etc/cockpit/parallel-ingress/apporo.json
python3 distribution/installer/parallel-ingress.py verify --instance apporo
python3 distribution/installer/parallel-ingress.py rollback --instance apporo
```

wrapper 透過 `brand_profile.select()` 選擇固定來源，再由 `prepare_source()` 複製、fetch 並驗證。staging 位於 `~/.local/state/woow-release/2026.11.15-rc1/parallel-ingress/branding/production/<commit>/`；不讀寫其上層主要安裝的 `brand.json`，也不建立假的 `device.json`。wrapper 沒有全域品牌切換、應用初始化、帳號 bootstrap 或資料卷操作。

install／verify／rollback 會準備並驗證來源，因此可能建立上述 staging 及讀取上游 Git；plan 才是完全不建 state 的來源查詢。wrapper 不以 root 執行整體流程，只在確認來源後將動作交給固定的 Cockpit CLI，例如：

```text
sudo env PYTHONDONTWRITEBYTECODE=1 python3 <pinnedCockpit>/parallel-ingress/manage.py install --config /path/instance.json
sudo env PYTHONDONTWRITEBYTECODE=1 python3 <pinnedCockpit>/parallel-ingress/manage.py verify --instance apporo
sudo env PYTHONDONTWRITEBYTECODE=1 python3 <pinnedCockpit>/parallel-ingress/manage.py rollback --instance apporo
```

config 以絕對路徑原樣傳遞，root 擁有權、schema、連接埠、後端 parity、交易與錯誤由 Cockpit CLI 負責。其非零退出碼會保留；失敗時不自動切品牌或退回未鎖定來源。rollback 作用於該 instance 的入口交易，不能當成應用資料、備份排程或全域品牌的回退工具；可回復範圍以該交易 journal 為準。

## 最終 pin 與驗證交接

兩品牌繼續共同指向 [2026.11.17-dual-brand.json](../brand-materials/2026.11.17-dual-brand.json)。最終 Cockpit 實作由主代理負責，本分工不猜測 commit／tree。取得已合併來源後，同時核對 repository、完整 commit、tree 及 `main_commit`，再提交材料鎖；未提交或被修改的材料鎖會被現有 `load_lock()` 拒絕。

來源驗證要求 commit 是釘選 main commit 的祖先，且該 main commit 仍位於 fetched `origin/main`。`parallel-ingress/manage.py` 不在既有四項 overlay 允許清單內，不能靠 staging 補一份 installer 或修改其內容來繞過最終 pin。也不修改歷史 `releases/2026.11.15-rc1/lock.json`、`materials.json` 或 `v2026.11.15-rc1` tag。

合併交接應包含：

1. 最終 Cockpit SHA／tree／main ancestry、root config schema、plan／verify／rollback 的實際結果及限制。
2. 同一組後端在 WOOW 與 Apporo 入口的管理、登入、備份與 Pi 功能證據；不以僅 HTTP 200 代替功能驗證。
3. 原 WOOW origin、全域品牌、既有 service owners、應用映像／資料／Secrets、Pi upstream 及原網路設定的保留結果。
4. instance 重跑、失敗恢復與 rollback，以及 public 相容別名和一般 LAN／VPN 路徑的隔離結果。

本 distribution 的本機檢查僅使用臨時 Git fixtures 與 mock root CLI：確認只讀來源計畫、production pin、來源漂移拒絕、原全域 receipt 保留、CLI 參數／退出碼與缺少 installer 時停止。測試不執行主機 sudo、Podman 或 systemctl；Cockpit 的實際入口與瀏覽器驗收仍由主代理提供。
