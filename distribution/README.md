# WOOW Ubuntu appliance — x86_64

這個目錄建立**全新設備**的 Ubuntu＋Podman／Quadlet＋品牌 Cockpit 與應用組合。它不是來源設備的磁碟複製或客戶資料還原，也不使用根目錄舊的 `scripts/restore.sh`。

第一個候選版是 `2026.11.15-rc1`。來源為 woowtechopenclaw 的正式服務組合，排除 Immich、測試容器、舊回退容器及私人登入。驗收狀態以同版 `releases/` 目錄中的紀錄為準；版本清單本身不是驗收通過的證明。

參考：[架構與版本邊界](docs/architecture.md)、[新設備驗收流程](docs/acceptance.md)、[既有設備的保留資料升級與只讀盤點](docs/existing-device-upgrades.md)。

## 安裝材料

需要兩部分：

1. 本公開倉庫：安裝器、來源 commit／映像內容鎖、預設設定、測試及文件。
2. WOOW 授權交付的 `images/`：品牌 HA、Odoo/JCR 及其他本機建置映像的 Docker／OCI 映像封存、SHA-256 清單。這些二進位材料不因本倉庫公開而自動變成可公開散布；不把私人原始碼或 registry 登入放進 GitHub。

安裝器驗證封存校驗碼，再確認載入後的 image config ID 與版本鎖相同。`manifest_digest` 是來源映像的 manifest digest；`id` 是 image config digest，兩者不可混用。OCI 匯出可能改變 manifest 的序列化／壓縮；封存本身另有 SHA-256。公開映像的線上來源以 registry digest 鎖定。匯入後使用本機 release 別名與 `Pull=never`；每次驗收再比對實際容器的 image config ID，不依賴匯出時可能改變的 registry manifest。`materials.json` 的校驗碼也必須符合本 Git release 內的可信索引。

首次安裝仍需網路取得固定提交的公開來源、Ubuntu 套件及原生 Pi 的釘選相依軟體。這不是完全離線的 OS ISO。安裝器固定 Podman、Cockpit 及 cockpit-podman 等關鍵套件版本；完整實際 apt 套件清單另外保存在設備的 `packages.txt`。

Office 外掛另外鎖在 `application-artifacts.json`：對齊來源設備的 richdocuments 12.0.1，使用官方發行封存與 SHA-256。`nextcloud-office-app.py` 檢查 Nextcloud 35 相容範圍、路徑、檔案類型及官方完整性簽章，再啟用外掛；拒絕覆蓋不同版本的既有 app。可用 `--archive /path/to/richdocuments-v12.0.1.tar.gz` 提供預先取得的相同材料，不再由 `app:enable` 自行選擇當時最新版本。這項 main 分支補充不改寫先前 rc1 tag。

版本鎖中的九個 Cockpit／Podman 套件設為 apt hold，需由維護者在下一個驗收版本明確更新；其餘 Ubuntu 安全更新仍依系統原有政策執行。安裝器另讓 needrestart 跳過有限期的 `woowtech-backup-j….service` 作業，避免更新函式庫時中止正在執行的備份／還原；下一個備份作業自然使用已更新的函式庫。這不會停用系統更新，也不排除其他常駐服務。

部署帳號的 systemd `user@UID.service` 關機等待時間設為 180 秒。Ubuntu 映像原本只有 5 秒，會早於 Quadlet 自己的 30–90 秒期限強制結束資料庫；不能只調容器內層的停止期限。OpenDesign 主服務另會在啟動前移除自己三個已命名的附屬容器，處理意外斷電留下的網路命名空間依賴；所有資料卷保留，不對其他容器執行 prune。

完整組合冷啟動時，EMQX 健康檢查改用容器內的節點 `/status`，避免每次 `emqx ctl status` 額外啟動 Erlang 程序而逾時；實際 MQTT 授權與讀寫另做功能驗收。Hermes 初始化等待 gateway 的期限延長至 900 秒，整機驗證也檢查初始化服務完成，不只看容器存在。完整組合與主機既有服務共享 N100 時，冷啟動可能需要十多分鐘；目前不宣稱固定秒數內就緒。

## 新設備安裝

準備 Ubuntu 24.04 x86_64、一個有 sudo 的一般帳號、至少 85 GiB 可用空間。完整參考機是 N100／16 GiB RAM；其他硬體及高負載容量不因 x86_64 相容就視為驗收完成。全新完整部署建議保留至少 120 GiB 給應用及後續資料。Podman 4.9 首次使用不同 UID 映射會產生額外映像副本，空間需求不能只用壓縮材料的 11.4 GiB 估算。若新設備沒有啟用 swap，平台階段會在 ext4／XFS 建立 4 GiB swap；既有 swap 保留。

```bash
git clone https://github.com/WOOWTECH/Woow_ubuntu_version_control.git
cd Woow_ubuntu_version_control
# 先 checkout WOOW 交付時記錄的 release commit/tag。
python3 distribution/installer/woow-release.py plan
python3 distribution/installer/woow-release.py apply \
  --materials /path/to/authorized-materials/images \
  --address <這台設備的區網IPv4>
```

安裝器不重新分割磁碟、不重設主機帳密，也不接管現有容器。若目標已經部署其他服務，應使用乾淨的設備或 VM；即使使用新 Linux 帳號，主機連接埠仍可能衝突，預檢會拒絕。

SSH 連線不穩定時，可在 `tmux` 中執行；或先執行 `platform` 完成 sudo 套件安裝，再將其餘階段交由該使用者的 systemd 執行。原生 Pi 第一次安裝也可能使用 sudo 安裝缺少的建置相依套件。

```bash
python3 distribution/installer/woow-release.py platform
python3 distribution/installer/woow-release.py sources --materials /path/to/authorized-materials/images
python3 distribution/installer/woow-release.py images --materials /path/to/authorized-materials/images
python3 distribution/installer/woow-release.py apps --address <區網IPv4>
python3 distribution/installer/woow-release.py office --address <區網IPv4>
python3 distribution/installer/woow-release.py native
python3 distribution/installer/woow-release.py cockpit --address <區網IPv4>
python3 distribution/installer/woow-release.py mcp
python3 distribution/installer/woow-release.py local-links
python3 distribution/installer/woow-release.py backup-catalog
python3 distribution/installer/woow-release.py verify
```

遇到失敗時依該階段的私有日誌修正，再執行同一階段。重新執行不覆寫已存在的設備設定或更換密碼；首次建置中斷不是執行 `uninstall` 或刪除資料卷的理由。

## 每台設備的帳號與授權

- Cockpit 使用新設備自己的 Linux 帳號；不內建共用帳號密碼。
- HA 新建立管理員及僅供這台 MCP 使用的權杖；管理員資料保存在 `~/.local/state/woow-release/2026.11.15-rc1/ha-account.json`，權限 0600。
- n8n 尚無擁有者時，建立此設備專用的管理員；資料保存在同目錄的 `n8n-account.json`。已完成設定的帳號不會被取代。
- Pi Web 使用此設備生成的密碼，保存在同一私有目錄的 `piweb-password`。保留 Pi Web 獨立登入。
- 各資料庫／應用／MCP 密碼由原專案安裝器生成為 Podman secrets，不輸出到公開報告。
- 模型供應商、PaaS／Cloudflare、ngrok、VPN 節點及外部 Kubernetes 需要新設備獨立授權。原設備的 Token、Tunnel ID、OAuth、MCP 設定中的外部憑證、Matter fabric、工作流程與使用者檔案都不複製。
- MCP 使用原部署已採用的未簽章發行流程，仍檢查來源是已合併提交、工作樹乾淨、建置標籤及映像 ID。它不是第三方簽署的供應鏈證明。

內部 Cockpit 使用 HTTP `:9090`，Pi Web 的 Cockpit 閘道使用 `:19094`。對外 HTTPS 由新設備的 Cloudflare／PaaS 授權設定；不繼承來源設備的網域和安全存取規則。

OpenDesign 的 Paseo bridge 程式已包含在相同映像中，但首次安裝預設關閉；原專案要求專屬 HTTPS origin 及允許清單。取得新設備的 HTTPS 網址後，設定 `OPENDESIGN_PASEO_ORIGIN`、`OD_ALLOWED_ORIGINS` 及 `WOOW_OD_PASEO=on`，再重跑 OpenDesign 安裝階段。這是等待新網址的設定差異，不能宣稱已完成 Paseo 外部連線驗收。

新設備會以當地生成的 MQTT 密碼把 HA 連上 EMQX，並將本機 HA MCP 加入 Pi／Claude Code／Codex 共用設定。EMQX 的 `woow` 帳號除了原有 `woow/#`，另可使用 HA 探索所需的 `homeassistant/#`；其他使用者主題仍拒絕存取。驗證指令 `python3 distribution/installer/local-smoke.py` 會建立短暫 MQTT 感測器，確認 HA 收到數值後移除測試資料，並驗證 MCP 與三代理設定。

原生 Pi 以新生成的 operator 帳號連到這台設備的 Omnigent，host 由持續運行的 Pi Web 服務管理。候選版對固定的 Omnigent plugin 0.3.31 加上一項明確覆寫：CLI 版本偵測由 5 秒延長為 30 秒；N100 VM 的 Pi 冷啟動曾實測超過 6 秒。覆寫會核對版本與原始程式片段，記錄變更後校驗碼，不變更登入、host 身分或模型授權判定。

`woow-native-connection.service` 隨 Pi Web 啟動，等本機 Omnigent 的 HTTP 健康檢查可用後，透過插件正式 `boot` 流程恢復已授權連線，並在冷啟動偵測失敗時有限期重試。它保留 host 程序所在的 systemd cgroup；Pi Web 停止時會一同停止。沒有登入紀錄、身分不符或使用者改連其他 server 時，不會偷偷登入或覆寫連線。

## 維護者製作材料

在**持有版本鎖中精確映像**且具散布授權的建置／參考設備執行：

```bash
python3 distribution/installer/export-materials.py \
  --lock distribution/releases/2026.11.15-rc1/lock.json \
  --output /private/woow-materials/images --all
```

`--all` 同時封存公開映像；本候選版的完整映像材料為 37 個檔案、約 11.4 GiB。匯出工具依來源格式保留 Docker／OCI 設定，另外讀取封存內的 config JSON，確認其 SHA-256 沒有改變。這個工具只讀取映像並執行 `podman save`，不匯出容器、資料卷、使用者家目錄或 Podman secrets。材料與其索引透過授權管道一起交付，接收方須使用可信的 Git release commit。不要以 `podman commit` 把現用容器轉成發行映像。

重製封存不保證壓縮後逐位元相同；交付本版時應保留已核對的 37 份原材料。若重新匯出的檔案 SHA-256 不同，須審查並發行新的材料索引／版本，不可叫接收方跳過驗證或自行修改可信索引。

## 首次操作

Cockpit 登入後，先在上方啟用管理存取權限，再開啟工具中的應用軟體、服務管理或備份還原。一般登入與管理權限是兩個階段；權限尚未開啟時，頁面會提示無法讀取服務。

各應用延續來源的監聽策略：HA、EMQX、n8n 與 Nextcloud 提供區網入口；其餘部分應用預設只監聽本機。尚未綁定 PaaS／Tunnel 的設備，這些應用需從本機或 SSH 轉送開啟；不可把來源設備的對外網址搬過來當成新設備入口。

## 版本與驗收

借鑑 HA 版本管理的「底座＋方案＋版本清單」模式，但 Ubuntu 使用 systemd／Quadlet，不包含 HAOS Supervisor。HA 品牌預裝映像與官方 HA Core 封裝分開記錄；不得用官方 Core 標籤替代 WOOW 預裝內容。

每次發版應新增 release 目錄，保留舊版鎖，不直接把 `main` 的最新來源當成舊版。先在乾淨設備安裝，再檢查首次初始化、映像身份、HTTP／登入、重複安裝、重開機、應用整合及備份還原。需要外部帳號、硬體或真實裝置的項目另外列出結果。

`verify` 對缺少容器、錯誤映像、未啟動或仍在 `starting` 的健康狀態回傳非零；HTTP 可連不等於模型對話、完整 Office 編輯或外網 VPN 測試成功。

```bash
python3 -m unittest discover -s distribution/tests -v
```
