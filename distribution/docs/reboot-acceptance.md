# 既有實體設備的重開機驗收

此流程在完成逐組升級後，檢查原設備的自動恢復能力。使用原本部署 Podman 的帳號；
不套用新機預設埠、不重設帳號，也不以新機 profile 排除原有應用。

## 重開機前

確認本機／遠端救援入口、部署帳號的 linger、服務開機依賴及資料庫停止期限。
排空正在執行的工作流程與備份，確認沒有進行中的套件安裝，並驗證已有回退備份。
`unattended-upgrades.service` 的常駐關機等待程序不等於正在更新套件；須檢查實際
apt／dpkg 工作及系統服務狀態，不可僅按程序名稱誤判或終止它。

外層 `user@UID.service` 的停止期限須涵蓋內層 Quadlet。已審查的
`overlays/user-manager.conf` 設定為 180 秒；只安裝到該部署帳號的 drop-in，
執行系統 `daemon-reload` 並讀回 `TimeoutStopUSec`。不用為此重啟使用者管理程序。
若已有其他 drop-in，先比對其優先順序與原有設定，不直接覆蓋。

用以下只讀工具保存實際運行基準。依設備實際網址與常駐服務提供參數；
工具會拒絕 root、未就緒基準及已存在的輸出檔案。

```bash
python3 distribution/installer/reboot-audit.py capture \
  --output "$HOME/private-reboot-before.json" \
  --unit pi-web.service \
  --unit woow-native-connection.service \
  --url cockpit=http://127.0.0.1:9090/ping \
  --url nextcloud=http://127.0.0.1:18080/status.php
```

基準包含所有正在運行的容器，不只發行方案中的容器。保存映像內容 ID、持久掛載、
連接埠、硬體映射、網路模式、systemd unit 及環境變數雜湊；不輸出環境值、命令列或
健康檢查日誌。共享網路命名空間以擁有者名稱比對，避免重建後的容器 ID 被誤判為
設定變更。動態 `HOSTNAME` 排除於環境比對，其餘環境變更均會使驗收失敗。

檔案權限為 0600，仍含設備路徑及網路配置，應保留私有。另為帳號、設定、裝置身分
及路由做應用專用比對；容器配置一致不能替代資料完整性驗證。

## 重開機後

由維護者在已授權的維護時段執行正常重開機。上述工具不會自行重開機、啟停服務
或更改設定。從其他設備觀察連線恢復，再執行：

```bash
python3 distribution/installer/reboot-audit.py verify \
  --baseline "$HOME/private-reboot-before.json" \
  --output "$HOME/private-reboot-after.json"
```

必須同時符合：同一主機與部署 UID、boot ID 已改變、所有原容器均恢復、沒有額外
容器、設定逐項相同、健康檢查就緒、指定常駐服務 active，以及 HTTP 入口回應 200。
缺少任何一項會回傳非零；不能只用 `podman ps` 或 SSH 已恢復宣稱成功。

等候期間只讀觀察，不人工重新啟動服務來替代自動恢復。若確實需要修正開機依賴，
保存首次失敗證據，修正來源與部署後再做一次實體重開機驗收。

就緒後另做真實功能測試，例如 HA MCP／MQTT 讀回、n8n queue／JavaScript runner、
Immich 本機推論、Nextcloud 結構與原帳號，以及 Cockpit／Pi Web 登入。若功能測試
本身需要重啟服務來註冊測試 fixture，必須放在只讀自動恢復驗收之後，並分開記錄。
以完成驗收時的開機 uptime 報告結果，不把它當成精確的網頁停機時間。

## 2026-11-15 實體 N100 結果

在原本已部署服務的 N100／16 GiB 主機上，先補齊該帳號的外層 180 秒停止期限，
再進行一次正常整機重開機。原 Matter、Tailscale、NPM、Immich 及新增服務全部保留。
原回退備份的 17 份檔案校驗通過；未執行資料還原或重設帳號。

| 驗收 | 結果 |
| --- | --- |
| 自動恢復 | 開機後 538.3 秒觀察到全部 53 容器健康；558.4 秒完成完整只讀驗收 |
| 配置一致 | 53 容器的映像 ID、持久掛載、網路、連接埠、硬體映射、環境雜湊與 unit 一致；沒有缺少或多出的容器 |
| 服務／入口 | 5 個指定常駐單元及 11 個 HTTP 入口全部通過；52 個具 systemd 標籤的容器單元 `NRestarts=0`；系統及使用者 failed units 均為 0 |
| 帳號／資料 | 118 份應用設定、28 份系統／帳號設定指紋一致；HA 帳號及裝置／實體 ID 保留，先前載入的 33 個整合恢復；n8n 與 Nextcloud 原帳號保留 |
| Pi 原生代理 | 自動連回本機 Omnigent，符合既有授權收據；Pi／Claude／Codex 可偵測，host PID 位於常駐連線服務 cgroup |
| HA／EMQX | MCP 發布唯一 discovery 與狀態訊息，讀回 23.75，清除測試保留訊息 |
| n8n queue | 原主入口及獨立 webhook processor 各執行一次，由 worker／JavaScript runner 回傳唯一結果；兩筆 DB 執行成功，測試流程移除，原帳號保留 |
| Immich ML | server 到 ML 可連；本機 CLIP 文字推論回傳 512 個有限且非全零的數值；不讀使用者相片 |
| Nextcloud | 35.0.3、維護模式關閉、cron 正常、官方 schema 零差異；原使用者數維持 1 |
| Cockpit／Pi Web | 原公開 HTTPS 及 VPN HTTP 可登入；應用卡片 14 張，桌面 1440px／手機 390px 無水平溢出；Pi 獨立登入通過 |
| 備份導覽 | 工具分類中緊接應用軟體；六個分頁與 24 個設定可讀取，桌面及手機無水平溢出 |

冷啟動期間曾出現尚未就緒的健康檢查，早期 HTTP 驗收中 Pi 逾時、LiteLLM 尚未接受
連線；該次失敗紀錄保留。等待後自行恢復，沒有透過手動重啟通過這項驗收。
關機時另有原桌面 Claude 程序等待逾時，外層 user manager 正常停止；這與資料庫
被外層 5 秒期限提前終止不同，不能混為同一問題。以上時間是採樣及完成驗收的 uptime，
不是精確對外停機時間，也不是所有硬體的開機效能保證。

n8n 功能測試在完整只讀自動恢復驗收之後執行。其官方 CLI fixture 發布／取消發布
需要重新啟動主服務、webhook 及主 runner 來刷新路由，這些測試用重啟不算入自動恢復
證據；原服務的開機成功已在此前獨立確認。最後取消發布並移除唯一測試流程，
再次比對原帳號、工作流程、憑證及設定。

完整無機密結果見[實體重開機證據](../releases/2026.11.15-rc1/evidence/physical-reboot.json)。
外部模型對話、所有 24 個應用的跨設備還原及大量業務資料遷移仍不在已驗收範圍。
