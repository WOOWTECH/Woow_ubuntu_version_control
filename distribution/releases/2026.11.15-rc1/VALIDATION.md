# 2026.11.15-rc1 驗收紀錄

本版在**第二台實體 Intel N100 上的全新 Ubuntu 24.04 VM**安裝；不是來源設備自測，也不是覆蓋第二台主機原有的應用。實體主機 16 GiB RAM，驗收 VM 配置 4 vCPU、10 GiB RAM、100 GiB 虛擬磁碟及 4 GiB swap。正式裸機重裝、實體主機重開機及其他硬體方案不在本次已驗收範圍。

以上為原始 VM 階段的範圍。後續已另行升級原實體設備並完成其重開機驗收，
見[實體設備紀錄](../../docs/reboot-acceptance.md)；兩階段證據分開保留。

公開證據僅包含版本、狀態、測試結論與不含帳密的畫面；原始日誌、備份檔、緊急金鑰及新機帳密保留在設備的私有目錄。

## 結果

| 項目 | 實測範圍與結果 |
| --- | --- |
| 安裝材料 | 37 份映像封存，逐份 SHA-256 與映像 config ID 相符；約 11.4 GiB，透過授權管道交付 |
| 版本組合 | 47 個正式容器、15 個來源提交、9 個 Cockpit／Podman 套件；比對版本鎖 |
| 原生 CLI | Node 22.23.4、Claude Code 2.1.296、Codex 0.162.1、Pi 1.4.0 |
| 上游應用測試 | 12 組操作 smoke suite 全部退出碼 0；未配置的外部服務依測試規則略過 |
| 重新安裝 | 重跑 12 組應用安裝，59 筆憑證／設定紀錄完全保留，新增密鑰數 0 |
| HA＋EMQX | MQTT discovery 建立臨時感測器、接收 23.75 狀態，測試資料清除 |
| HA MCP／三代理 | MCP 初始化與工具清單成功（開機前 73 項、第二次開機後 72 項，依當時 HA 提供能力）；Pi、Claude Code、Codex 使用相同本機 HA MCP 設定 |
| n8n queue | 真實 production webhook → queue worker → JavaScript runner 回傳唯一結果；測試流程停用、封存、刪除 |
| Nextcloud／Odoo | 新機管理員憑證可用；WebDAV 寫入／讀回／刪除成功，Collabora discovery 可用，Odoo tenant 管理員登入成功 |
| EMQX 備份還原 | 加密冷備份、深度驗證、下載校驗、資料卷內容核對、修改 retained 訊息後實際還原舊值成功；保留還原前安全備份 |
| Cockpit 部署 | 127 個管理檔案、5 個目錄與品牌來源版本 2026.11.15.2 一致，drift 0 |
| 修正後重開機 | 第三次開機後 47 容器恢復、版本鎖與功能測試通過；原主機同時跑既有服務與 VM，最終驗證在開機後 1,366 秒完成。初次 queue 探測曾因 runner 尚未註冊失敗，等待註冊後重測成功，未重啟服務掩蓋問題。 |
| 最終瀏覽器驗收 | 13 張應用卡片均顯示執行中；桌面 1440px／手機 390px 無水平溢出。Pi Web 獨立登入與深淺色同步通過；備份頁實際下載 40 KiB 檔案。 |

證據索引：[機器檢查與功能測試](evidence/functional.json)、[瀏覽器驗收](evidence/browser.json)、[畫面](evidence/screenshots/)。

## 新機實測發現並納入的修正

1. **首次啟動**：保留 Docker／OCI 映像格式與 config ID；延長 keep-id 首次映像 UID 映射的等待時間；處理 Odoo 全新資料庫初始化、LiteLLM Prisma、Nextcloud cron 啟動時序及 Cloudflare GUI 首次設定。
2. **備份驗收**：EMQX 的 `/readyz` 僅供容器內使用，主機檢查改用入口 `/healthz`，另要求已授權 MQTT 真實讀寫。HA MCP 的 GET `/mcp` 預期是 405；另做真正的 MCP 協定測試。Mosquitto 發布被拒仍可能退出 0，測試改為 MQTT 5、檢查錯誤輸出及實際讀回內容。
3. **系統更新**：Ubuntu 安全更新曾透過 needrestart 中斷備份工作；現在僅排除這類有限期的備份作業，下一次作業會使用更新後函式庫。九個版本鎖套件設為 apt hold，其餘 OS 更新政策保留。
4. **正常關機**：第一次重開機發現 Ubuntu 的外層 `user@UID.service` 只等 5 秒，會先於 Quadlet 的停止期限終止應用。現改為此部署帳號等待 180 秒。OpenDesign 啟動前另清除自己三個附屬容器，避免意外關機殘留的網路依賴阻擋主容器；不刪資料卷或其他應用。
5. **原生 Pi 恢復連線**：N100 的 Pi 冷啟動查版本曾耗時 6.05 秒，原有 5 秒偵測會誤判。固定版插件改為 30 秒，並記錄覆寫校驗碼。增加等本機 Omnigent 就緒的連線恢復服務，透過原插件驗證既有授權及 host 身分；不自動重登、換身分或呼叫模型。
6. **冷啟動健康檢查**：EMQX 的 CLI 已回報啟動，整個檢查程序卻超過 10 秒；改用現有入口也使用的容器內節點 `/status`，實測回應 200，連同 Podman exec 約 1.46 秒。Hermes gateway 冷啟動曾晚於初始化腳本原有的 300 秒期限，改等 900 秒，並把初始化 unit 納入整機驗證。容器狀態採一次批次讀取，減少 47 次 Podman 程序啟動。

7. **queue 執行器準備狀態**：第三次冷啟動中，HTTP health 已正常但 JavaScript launcher 尚未註冊，第一筆驗收工作逾時。驗收程式新增註冊等待，再建立唯一的測試工作流程；不對失敗的工作自動重送。此等待是驗收門檻，並未宣稱上游 HTTP health 已能表示所有 runner 都就緒。

首次失敗與中斷的備份／重開機紀錄仍保留於驗收 VM，沒有以刪除歷史來替代修正。VM 後續離線封存以釋放實體主機資源；不影響其原有應用資料。

## 必須分開看待的邊界

- 這是全新應用環境，沒有搬移來源設備的業務資料、OAuth、SSH host key、Tunnel 或 Matter fabric。新機身分與來源設備不同。
- 這次實際還原的是 **EMQX**；22 組備份目錄已配置，不代表另外 21 組或跨設備資料還原都完成演練。原生 Pi 全部家目錄、Ubuntu OS、code-server 部分工作目錄不在這份自動目錄的完整覆蓋範圍，詳見[驗收與備份說明](../../docs/acceptance.md)。
- 模型供應商、PaaS／Cloudflare、ngrok、VPN 節點與 Kubernetes 需新設備另行授權。沒有宣稱已在新機完成真實模型對話、外網 VPN 或對外 HTTPS／PWA 安裝測試。
- 九個額外 MCP 服務驗證的是管理頁、登入／拒絕錯誤權杖與管理功能；未設定的業務後端不算已通過 MCP 操作驗收。自動接通且實測的是 HA MCP。
- Nextcloud 已驗證檔案操作及 Office discovery，沒有把它當成完整 Office 文件編輯測試。OpenDesign 的 Paseo bridge 待新設備專屬 HTTPS origin 設好後啟用。
- VM 使用 NAT；單一 Cockpit 轉送埠不等於每個應用入口都轉送。完整頁面驗收透過 SSH SOCKS 進入客體網路。裸機安裝應使用自己的區網 IPv4，另設定外部入口。
- 鎖定的是應用映像、來源提交及關鍵套件。Ubuntu 核心與其餘 OS 套件可依安全更新變動，這不是逐位元相同的 OS ISO。未完成整個私人映像檔案系統的機密／授權稽核；二進位材料維持授權交付，未公開上傳。
