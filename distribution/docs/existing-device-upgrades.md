# 既有設備的保留資料升級

## 與全新安裝分開

`woow-release.py apply` 只適用全新環境，不能用來接管正在使用的設備。不要移除其「已有容器／Quadlet」保護，也不要建立假的 `device.json` 繞過預檢。

既有設備的目標是延續原服務的資料、帳號、密鑰、裝置配對與入口網址。這和把來源設備的私密資料複製到新設備不同。版本更新涉及資料庫遷移，不能以更換舊映像當作完整回退。

目前提供只讀盤點，並已完成一台既有設備的 n8n、Home Assistant、Nextcloud、Pi、Cloudflare Tunnel 與 Cockpit 升級實測；**本候選版尚未提供已驗收的整機原地升級命令**。各應用來源中已有專用升級／回退腳本，仍需對照設備現況、準備一致的備份，在隔離副本測試後才可用於正式切換。

```bash
# 使用原本部署 Podman 的帳號執行；不使用 sudo 或新帳號。
python3 distribution/installer/upgrade-audit.py \
  --output "$HOME/woow-upgrade-audit.json"
```

報告包含容器映像內容 ID、狀態、資料掛載、連接埠及 Quadlet 依賴；不輸出環境變數值、命令列、任意映像標籤或 Podman secret 內容。報告以 0600 新建，拒絕覆寫既有檔案，因含設備路徑與網路配置應保留私有。命令只查詢服務，不會停止、建立、刪除容器或資料卷；報告不是升級核准或相容性通過證明。

## 第二台 N100 的差異實例

2026-11-15 的只讀盤點找到 16 個運行中容器及 17 個停止的舊容器。下表不是完成升級的紀錄。

| 服務 | 原有部署 → 候選版 | 升級必須處理的內容 |
| --- | --- | --- |
| Home Assistant | 原生 Core 2026.9.1 → WOOW 2026.9.1-r7 預裝映像 | 保留 `/config`、使用者與 `.storage`；比對既有 ZHA、HomeKit、Matter 等整合，不重新 onboarding |
| Nextcloud | 34.0.3 → 35.0.1／Office | 確認 34 系列最新維護版及第三方 app 相容性；資料庫與程式一起備份、一起回退；原有 bind mounts 及網址繼續使用 |
| n8n | 2.38.7 → 2.43.6 | 保留資料庫、加密金鑰及擁有者；主程序與 runner 同版；更新版本與改 queue 拓撲分開驗收 |
| Pi Web | Podman 套件 0.9.0-r1 → 原生套件 0.2.7 | 不同專案版本不能按數字比較；需遷移會話、專案路徑、登入及代理身分，並避免兩邊同時寫入 |
| Cloudflare Tunnel | 1.1.0 → 1.2.1 | 延用原 Tunnel、路由與 Access 設定，使用來源專用的獨立 watchdog 升級／回退流程，防止 SSH 中斷讓升級停在半途 |
| Matter、Tailscale、Nginx Proxy Manager、Immich | 原設備另有服務 | 原樣保留並審查依賴；不因新機 profile 排除某套件就移除原設備的服務 |

原 Nextcloud 使用 `:18080`，而全新方案的 Odoo 也預設用此埠。既有設備應保留 Nextcloud 入口，為新增 Odoo 分配另外的埠；不能直接套入新機預設設定。原 Pi Web 的反向代理與 CF 路由也須跟著內部服務位置調整，而不是要求使用者換網址。

## n8n 實體主機升級紀錄（2026-11-15）

已獲設備擁有者確認：升級原服務、可短暫停止、資料與網址必須保留。先用私有快照在無對外連接埠、禁止網路對外連線的副本上升至 2.43.6，再用同一快照恢復 2.38.7；兩次均可啟動，原帳號及加密金鑰一致。

正式切換時先停止 n8n 與 runner，保留 PostgreSQL 運行以取得一致邏輯備份，包含 DB、角色、資料卷、金鑰、環境檔與單元；校驗備份後才執行固定來源的 `scripts/upgrade.sh --yes`。新版主程序與 runner、JavaScript／Python 註冊、資料庫就緒與 HTTP 測試全部通過。原環境檔、連接埠、掛載與帳號資料逐項比對一致。切換至完成驗證共 112.5 秒，這不是精確 HTTP 停機秒數。

此設備有 1 個使用者、0 個工作流程及 0 筆第三方憑證，不能據此宣稱已驗證含實際業務內容的遷移。既有外網入口未登入時仍回 403；保留其路由／設定，不把這視為外網授權登入驗收。這次只更新版本，queue 拓撲另行切換驗收。

後續另取完整冷備份，才啟用 Valkey、worker、worker runner 與獨立 webhook processor。主程序仍接收原有 production webhook，沒有要求既有網址更換路由。原帳號、工作流程、憑證、加密金鑰及 PostgreSQL image ID 比對一致。以 n8n 官方 CLI 匯入／發布唯一的暫時測試工作流程，不猜測或重設擁有者密碼；原主入口與獨立 webhook processor 各執行一次，兩次皆由 queue／JavaScript runner 回傳唯一結果，資料庫紀錄成功，最後取消發布並移除測試內容。

PostgreSQL 16 在 n8n 2.43.6 中會提示僅提供相容支援，仍保留此設備與 rc1 profile 的 16.15。這不是 PostgreSQL 跨主版本升級驗收；若要移到 17 以上，應另做 dump／restore 演練，不能直接更換資料庫映像。

Nextcloud 34 系列於查核日最新維護版為 34.0.6，既有 34.0.3 應先升至此版，再升到候選版 35.0.1。[Nextcloud 官方發行目錄](https://download.nextcloud.com/server/releases/)。

## HA、Tunnel 與 Cockpit 實體升級紀錄

Home Assistant 由原生 2026.9.1 切換至固定 WOOW 2026.9.1-r7 映像。先在無網路副本檢查原設定及品牌映像，再以來源的冷備份升級程序切換。透過原設備已有的 HA MCP 比對，31 個原本已載入的整合全部恢復；原帳號、密碼紀錄、裝置與實體 ID、YAML、環境檔、硬體映射及獨立 Matter 程序均保留。升級及驗證共 250.5 秒；沒有對真實裝置發送控制指令，也沒有把原先未載入的整合算成修復成功。

既有設備不能直接覆蓋品牌預裝檔案。新增 `installer/seed-existing-ha.py`：等版、較新或無法辨識版本的自製整合保留整棵目錄，避免混入較舊檔案；較舊整合可加入新版檔案，保留使用者額外檔案；既有 YAML、佈景、藍圖與前端資源不覆寫。本次保留設備較新的 HA MCP 1.3.2，沒有降至映像內的 1.2.2。此腳本只作為已備份的專用升級流程覆寫，不自動套用到未知設備。

Cloudflare Tunnel 1.1.0 升至鎖定的 1.2.1 映像，先備份資料及路由基準，再使用獨立 watchdog 切換。新程序維持 4 條連線、原路由映射、設定版本及各網址原有 HTTP 回應，觀察後成功提交；SSH 斷線後可恢復。原 Tunnel／Access 設定未重新綁定。升級及觀察共 220.2 秒，不等於精確的外網停機時間。

Cockpit 314 升至 362、Podman 插件升至 124，並安裝固定品牌版 2026.11.15.2。原帳號、密碼與對外 origin 保留，補上明確的區網及 VPN HTTP origins。使用原帳號經公開 HTTPS、區網 HTTP 及 VPN HTTP 登入並取得管理員權限，6 張現有應用卡片可讀取；1440px／390px 無水平溢出。Immich 等原設備額外服務保留，其既有健康異常不因卡片顯示執行中就算修復。

版本鎖使用 `apt-mark hold` 後，dpkg 會回報 `hold ok installed`。舊 Cockpit 品牌安裝器誤認為未安裝，修正已合併至 [Woow_cockpit PR #13](https://github.com/WOOWTECH/Woow_cockpit/pull/13)，32 項安裝測試與 CI 通過。本版本的固定來源由 `installer/patch-cockpit-held-packages.py` 套用相同相容修正；仍拒絕過舊或未配置完成的套件，不解除版本鎖。

後續完整實體設備的新增服務與跨服務結果見下方紀錄；VM 驗收與實體驗收各自列出。私有備份、原始日誌及金鑰不放入公開倉庫。

## Nextcloud 與 Pi 實體切換

Nextcloud 的隔離副本先以完整備份完成 34.0.3 → 34.0.6 → 35.0.1，再還原為 34.0.3，確認原帳號、設定及檔案一致。正式設備分兩階段升級，每次均驗證完整冷備份的校驗碼；原帳號密碼、instance secret、資料掛載、對外連接埠及網址保留。兩階段升級與驗證分別花費 359.3、446.5 秒，不是精確 HTTP 停機時間。此設備當時只有一個使用者、零個實際使用者檔案，不能據此宣稱已完成大量既有文件遷移驗收。

Pi 由舊 Podman 套件切換至固定原生套件，保留 14 份會話、原模型登入與 MCP 設定、套件清單及專案檔案。舊工作目錄絕對路徑以明確的相容 symlink 延續；複製使用 `podman unshare`，避免容器 UID 擁有的檔案遺漏。固定原生 Omnigent／Paseo 插件加入既有套件清單，不刪除原套件。既有 NPM 路由仍指向原容器名稱與連接埠，由僅位於原私有網路的相容代理，透過使用者 socket 轉到 loopback 上的原生 Pi；NPM 設定與外網路由均未更名。

Pi 切換與驗證花費 86.7 秒。14 份會話與模型／MCP／專案內容雜湊一致，另核對舊工作目錄的 12 個檔案；原資料卷沒有運行中的寫入者，並另作完整壓縮備份、驗證壓縮檔與校驗碼。舊套件的健康檢查 timer 原本執行 `podman healthcheck run pi-web`，遷移後該名稱是無容器健康探針的相容代理，會產生 exit 125；已保留原 30 秒週期、改查原生 Pi HTTP 端點並驗證成功，不因此重啟 Pi。舊 Pi 沒有獨立網頁密碼，新版新增設備專用的 Pi Web 密碼；這不更動模型供應商登入。桌面與手機可登入，但本階段沒有對外模型對話驗收，也沒有宣稱舊設備本來不存在的 Claude／Codex 登入已完成。

Office 另外使用固定 richdocuments 12.0.1 官方封存、SHA-256 與 app 完整性驗證啟用，Collabora discovery／capabilities 已通過。原 Nextcloud `:18080` 由 gateway 延續，app 本身移到 loopback 的 `:18082`。原帳號、掛載與網址比對一致。另以暫時帳號經原區網入口開啟 DOCX，在 Collabora 內輸入唯一識別字並儲存，下載 DOCX 後解析 Word XML 的文字節點，確認完整內容已寫入；最後刪除測試帳號及檔案，使用者數恢復為原本的一位。Office 的 VPN 文件編輯仍未驗收。

備份時另發現 UID 33 擁有、0700 的 HTML 目錄，讓主機使用者的 `-d html/config` 誤判設定不存在。完整冷備份的 `html.tgz` 仍含設定，但一般備份可能漏掉獨立的 `config.tgz`。修正已合併至 [Nextcloud PR #8](https://github.com/WOOWTECH/Woow_podman_nextcloud/pull/8)：目錄檢查與封存均在 Podman user namespace 內執行，設定無法讀取時直接失敗，封存權限設為 0600。真實 UID 權限測試與 CI 通過，實體設備另比對原 `config.php` 和封存內容雜湊一致。`patch-nextcloud-backup.py` 將同一修正套入固定來源，既有補丁可重複呼叫，不改寫 rc1 tag 或共用 Quadlet library。

## 保留 Cockpit 網址的 PWA 與 Pi 入口

既有 Tunnel 原本指向 Cockpit 的 `:9090`。此設備讓 PWA gateway 接手原連接埠，Cockpit backend 改為僅限 loopback 的 `:9092`，保留原 Cloudflare hostname、Tunnel 路由、Access 設定及 Linux 帳號。gateway 仍驗證 Cockpit session 與 Pi 自己的登入。區網與 VPN 使用 HTTP，外網 HTTPS 由原 Tunnel 提供。

設備的 userspace VPN 沒有在 Linux interface 上配置 VPN IP。新增明確 opt-in 的 loopback forwarding，維持精確的 VPN Host／Origin 與登入檢查；既有 VPN 身分與其他轉送保留。Cockpit browser port 和 backend port 分開設定，避免 iframe policy、主題訊息誤指到內部埠。修正與安全測試已合併至 [Woow_cockpit PR #14](https://github.com/WOOWTECH/Woow_cockpit/pull/14)。這是既有設備的入口適配，不改寫原 rc1 tag 的來源鎖。

區網、VPN 的滑鼠登入、Pi 操作頁、390px 排版與藍色深淺主題同步已通過。公開 HTTPS 的登入、主題與版面也通過；一般瀏覽器設定檔的測試使用 DOM 表單送出，因自動化滑鼠／鍵盤事件未送達巢狀 iframe，此限制保留在證據中。早先無痕瀏覽器的公開入口登入成功，但無痕模式不允許安裝 PWA；另以一般設定檔確認瀏覽器回報零項 PWA 安裝阻礙。後續使用獨立 Chromium 設定檔實際安裝 PWA、設定「以視窗開啟」、啟動並驗證 `display-mode: standalone` 與 Cockpit 登入；此項以 DOM 操作登入控制項。不把這些測試擴大為所有手機／瀏覽器均已實機驗收。

同名映像標籤也可能對應不同內容。實測在匯入其他服務前發現原 PostgreSQL、Redis 有相同版本標籤但不同 image ID，因此先為原程序建立固定本機映像參照，避免下一次重啟意外換成另一個建置；資料庫不因新增服務而被順帶更換。

## 升級門檻與驗收

1. 先確認要升級的服務與可接受的中斷時間；一台設備逐組切換，不同時中斷所有應用。
2. 記錄映像 ID、資料路徑、帳號／設定指紋、入口、整合狀態、資料庫版本與遷移版本；禁止在公開報告中放實際金鑰。
3. 預先取得並驗證新映像；確認磁碟足以同時保留新舊映像、備份及失敗現場。不可用刪掉唯一舊資料來騰出升級空間。
4. 用隔離副本演練升級與回退。HA 副本不可連真實裝置；n8n 副本不可啟用原排程、webhook 或對外副作用。
5. 切換前停止新的寫入、排空背景任務，取得一致的最終備份。資料庫、加密金鑰、檔案與版本設定要能一起還原。
6. 套用應用專用升級路徑。禁止讓舊、新程序共寫同一份已遷移資料庫；PostgreSQL 跨主版本另走 dump／restore，不能直接換映像。
7. 確認原使用者登入、資料數量與內容、裝置整合、原網址、背景任務及重開機後恢復。失敗時先停止新版寫入，再依演練流程還原。

「資料與使用方式延續」不等於「零中斷」。Nextcloud 官方明確要求升級期間進入維護模式，且不支援直接降版。[Nextcloud 升級說明](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/upgrade.html)。n8n 官方要求相關程序協調更新、runner 同版，回退時要處理資料庫遷移；不能保證混用版本不中斷。[n8n 更新說明](https://docs.n8n.io/deploy/host-n8n/keep-n8n-running/update-n8n.md)。

## 已有的應用升級入口

來源均需使用版本鎖對應的提交；先閱讀腳本及設定，不能直接照抄執行於未知設備。

| 固定來源 | 升級實作 | 本機切換前仍須驗證 |
| --- | --- | --- |
| `Woow_podman_homeassistant` | `scripts/upgrade.sh`：冷備份、前後整合比對、失敗回退 | 品牌預裝與現有自製整合的合併；Matter 與實體設備身分 |
| `Woow_podman_nextcloud` | `scripts/upgrade.sh`：版本閘、冷備份、HTML＋DB 回退 | 完整檔案備份、最新維護版、第三方 app、Office 與既有路由 |
| `Woow_podman_n8n` | `scripts/upgrade.sh`：版本一致性、DB 備份、回退 | 保留加密金鑰、既有環境設定與工作流；獨立驗收 queue 切換 |
| `Woow_cloudflare_tunnel_webgui` | `scripts/upgrade.sh --prepare-only` 與 `swap`：獨立 watchdog、連線／路由 gate、觀察與回退 | 既有 CF 授權及對外網址、SSH 恢復、資料格式相容性 |

最終升級紀錄應另外列出每個服務的舊／新版本、備份校驗、回退演練、實際中斷秒數及資料驗證結果；新 VM 的安裝驗收不能替代這份紀錄。

## Nextcloud Text 的既有資料相容修正

此設備經 34.0.6 升至固定的 35.0.1 後，文字編輯 session API 回報 `lastAttachmentCleanup is not a valid attribute`。34.0.6 內附 Text 8.0.1 已建立 `last_attachment_cleanup`，但 35.0.1 內附的 Text 9.0.0 不認識此欄位。這不是使用者文件損壞；不可刪除欄位來隱藏錯誤，也不可裝回只支援 Core 34 的 Text 8。

官方 35.0.3 封存中內附、支援 Core 35 的簽章 Text 9.0.2 可用來修正這條既有升級路徑。`application-artifacts.json` 固定其官方封存 URL 與 SHA-256；以下命令只驗證、擷取 app，不變更運行中的服務，也不把 Core 映像改為 35.0.3：

```bash
curl -fL --retry 3 -o nextcloud-35.0.3.tar.bz2 \
  https://download.nextcloud.com/server/releases/nextcloud-35.0.3.tar.bz2
python3 distribution/installer/prepare-nextcloud-text.py \
  --server-archive nextcloud-35.0.3.tar.bz2 \
  --output nextcloud-text-9.0.2.tar.gz
```

套用前須完成包含 DB、HTML、使用者檔案、config 與密鑰的冷備份並驗證校驗碼；停止 cron、啟用維護模式後，以已驗證的官方 app 替換原 Text，執行 `occ integrity:check-app text` 與 `occ upgrade --no-interaction`。不得手動刪改資料庫欄位。重新啟動 app 清除 PHP opcode cache，恢復 cron，核對原帳號／instance key／網址，並以瀏覽器編輯及 WebDAV 讀回驗收。失敗時以同一份完整 HTML＋DB 備份恢復，不能只換回舊 app 程式。

這是既有設備的可選修正，並未改寫 rc1 的 Core image ID 或歷史 tag。實體功能驗收結果以證據檔為準。

實體驗收另確認：Nextcloud 的 `occ upgrade` 會嘗試從 App Store 更新已啟用的應用，這次同時將 richdocuments 升到官方 12.0.2。已另外鎖定其官方封存、核對 app 簽章，並重新完成 DOCX 編輯／儲存／下載比對；不把先前 12.0.1 的結果當作新版測試。全新設備的 Office 12.0.1 pin 保留，既有設備的 12.0.2 例外列在 `application-artifacts.json`。往後維護時應盤點全部 app 的實際版本，不能只核對 Core 映像。

Text 9.0.2 已通過瀏覽器 session API 200、編輯與 WebDAV 讀回驗收，暫時使用者與檔案已清除。Office／gateway 的 Quadlet 同時加入 `nextcloud.target` 的 `WantedBy`，讓整組停止後能一起恢復，不只隨 `default.target` 啟動。實體整組重啟後 29.7 秒達到穩定就緒，Office／gateway 無須手動啟動；一秒間隔探針觀察到約 22.6 秒不可用區間，這不是精確停機秒數。原帳號、密碼、金鑰與網址指紋一致。

此升級路徑另遇到 [Nextcloud 上游 #64487](https://github.com/nextcloud/server/issues/64487)：修復步驟移除空的 `federated_invites` 表後，結構檢查仍期待該表。實體設備先取 DB dump 並校驗，再用隨該版本出貨的 `cloud_federation_api/1016Date202502262004` migration 重建缺少的空表。`repair-nextcloud-invites.php` 預設只預覽，限定 35.0.1、僅允許建立該表及其 token 唯一約束；明確加上 `--apply` 才會執行。原帳號、密碼、資料列及既有索引未刪除。該階段仍保留兩個舊版額外索引 `taskp_tasks_scheduled`、`text_steps_doc_id_id_index` 的結構提示，**當時尚未通過 schema 檢查**；後續維護與收尾結果見[維護紀錄](maintenance-closeout.md)。[官方 schema 檢查說明](https://docs.nextcloud.com/server/stable/admin_manual/occ_database.html#db-schema-check)提醒部分差異可能有效，應逐項審查。

本輪也遇到大量映像匯入與 rootless UID 初始化爭用 Podman 儲存鎖，拖延冷備份的停止程序。已將後續流程改成所有映像準備完成後才安裝／切換服務；Text 修正連同完整備份與等待共 689.8 秒，並非精確 HTTP 停機秒數。不能把這次保留資料升級描述為零中斷或全程秒級切換。


## 實體設備完成驗收

保留原服務後，補上 Omnigent、LiteLLM、EMQX、Odoo tenant cloud、Hermes、OpenDesign、Headscale 與 code-server；8 項來源 smoke 全部通過，另有 9 項 MCP 管理服務通過各自安裝檢查。37 個固定映像均已核對內容 ID。原有的 Matter、Tailscale、NPM 與 Immich 保留，最終共 53 個運行中容器；該階段原本 Immich machine-learning 的 unhealthy 狀態仍在，沒有把它算成修復；後續獨立修復及推論驗收見[維護紀錄](maintenance-closeout.md)。

新 Odoo 使用另配的 `:18084`，原 Nextcloud `:18080` 延續。Cockpit 保留原帳號、網址與既有自訂連結；14 張應用卡片在 1440px／390px 顯示與管理資料讀取通過，沒有水平溢出。已填入本機／區網／VPN 可使用的應用入口與原本的對外網址，沒有替原 Access 規則解鎖。Hermes 卡片使用管理頁 `:19119`（不是 gateway API 的 `:18642`），以設備專用密碼完成實際瀏覽器登入。

原生 Pi 保留既有模型登入與 MCP 項目，加入本設備 HA MCP；Pi／Claude／Codex 的 HA MCP 設定一致，可列出 77 個工具。以本機 operator 連接新 Omnigent，三種代理均可偵測。實測發現首次 host 留在暫時安裝作業的 cgroup，作業結束後會被清掉，因此另在作業退出後重啟常駐 `woow-native-connection.service`；再次確認 host ID 未變、保持連線，實際 PID 屬於常駐服務。此項沒有呼叫外部模型。

HA 接上新本機 EMQX，原整合保留；透過 MCP 發布唯一的 MQTT discovery／狀態訊息，讀回 `23.75`，再清除保留訊息。初次查詢早於 discovery 完成時會回 entity-not-found，驗收已改成等待實體出現，沒有把暫時未出現當成成功。

Cockpit 裝入 24 個備份應用設定，保留冷備份策略。Pi bridge 與 Cockpit PWA 是入口輔助服務，其設定未包含在推測的 app 備份範圍，因此沒有誤列為完整可還原套件。code-server 的應用資料可備份，但主機 `Desktop`、`.ssh`、`.local/bin` 與 `.gitconfig` 不在這個備份範圍；原生 Pi 也應使用其原生資料備份，不能以 bridge 的備份代替。這不是 24 個應用都已各自完成跨機還原演練的宣稱。

上述階段尚未做實體整機重開機；後續已完成，結果另見[實體重開機驗收](reboot-acceptance.md)。仍未驗收外部模型對話、外部 Headscale 節點或所有 SaaS 的第三方授權。全新隔離 VM 的冷啟動、備份下載與還原結果另列。新服務密碼只存於設備的私有交接檔，公開版本不包含原設備／來源設備的帳密、Tunnel token、模型供應商權杖或使用者資料。

## 後續維護與來源同步

Nextcloud 35.0.3、原設備 Immich ML 修復及 Cockpit 備份導覽的版本、限制、操作方式與證據，集中於[維護收尾紀錄](maintenance-closeout.md)。歷史階段結果與 rc1 新機版本鎖保留，不把後續維護測試回填成當時已通過。
