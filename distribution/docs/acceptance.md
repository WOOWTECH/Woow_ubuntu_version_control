# 新設備驗收與交付

驗收必須針對新安裝的設備執行。不要把同一台來源主機的健康狀態當成新設備已可復現的證明。執行紀錄在安裝帳號的 `~/.local/state/woow-release/2026.11.15-rc1/`，預設為私有檔案。

## 版本、服務與本機整合

```bash
python3 distribution/installer/woow-release.py verify
python3 distribution/installer/smoke.py
python3 distribution/installer/local-smoke.py
python3 distribution/installer/queue-smoke.py
python3 distribution/installer/app-smoke.py
python3 distribution/installer/resume-smoke.py
```

- `verify` 比對 47 個正式容器的映像內容 ID、運行／健康狀態、關鍵 Ubuntu 套件版本、本機 systemd 服務及 HTTP 入口。缺項會傳回非零狀態。
- `smoke.py` 使用各固定提交的原專案測試。它不呼叫外部模型；Cloudflare 尚未綁定時，外網連線檢查會明確跳過。
- `local-smoke.py` 驗證 HA 經 EMQX 自動探索臨時感測器並接收數值，測試後清除 retained 訊息；另檢查 HA MCP 與三代理共用設定。
- `queue-smoke.py` 使用新設備 n8n 擁有者登入，建立臨時 webhook／Code 流程，經正式 webhook processor、queue worker 與 JavaScript runner 取得唯一回覆，再停用、封存及刪除流程。
- `app-smoke.py` 用新設備憑證在 Nextcloud 寫入、讀回及刪除一個測試檔，驗證 Collabora discovery 及 Odoo tenant 管理員登入。這不是完整 Office 文件編輯驗收。
- `resume-smoke.py` 會重跑應用安裝階段，可能重新啟動服務；它在記憶體中比對 Podman secrets 及新機帳號檔案的雜湊，報告只記錄是否保留，不輸出密碼或雜湊。

自訂過帳號、網址或模型之後，應相應調整驗收設定；不要為了讓測試通過而覆寫客戶的設定。測試報告不能把「未授權、未綁定」改稱功能已實測。

## 備份與還原演練

Cockpit 的備份目錄由 `backup-catalog` 根據此設備的 Quadlet 產生，預設使用整組停止的冷備份。檢查私有 `backup-catalog.json` 裡的 `skipped` 與 `warnings`，確認資料範圍；它不備份 Ubuntu 本身或原生 Pi 的全部家目錄。

本候選版首次盤點為 22 組。code-server 的 `Desktop` 工作目錄、`.ssh`、`.local/bin`、`.gitconfig` 預設未納入；Headscale／OpenDesign 的執行期 socket 資料卷也排除。PWA gateway 的靜態 nginx 設定由本發行版重新安裝，未納入其自動建議的備份項目。這些排除不能當成完整工作站備份；開始放入客戶資料前應確認工作目錄的獨立備份。

資料庫映像用內容 ID 別名固定，所以自動盤點仍會提示標籤不像 `postgres:16`；還原依舊必須使用相同版本鎖。`TOKEN_DIR`、`MIN_OUTPUT_TOKENS`、`CREDENTIALS_PATH` 等變數名稱也會觸發提示，它們是路徑／設定值，不是已發現外洩的密碼；不要為消除提示而放寬備份引擎的檢查。

以下會短暫停止整組 EMQX，並真的還原其資料，只能在這次新建的隔離驗收設備使用：

```bash
python3 distribution/installer/backup-smoke.py --confirm-isolated-device
```

演練會建立測試 retained 訊息、加密備份、深度校驗、讀取可下載檔案的校驗碼，再改變訊息並還原備份，確認舊值恢復；還原引擎須保留安全備份。測試後移除臨時 MQTT 訊息。測試用 Mosquitto 映像由 EMQX 的完整 smoke suite 先取得。

交付時讓設備管理員到 Cockpit「備份與還原」下載並妥善保存緊急金鑰。不要把緊急金鑰、備份內容、帳密檔案或原始日誌提交至公開 GitHub。

## 重開機與重新執行

先記錄 `verification.json`，再重開**驗收設備**，等各服務啟動後重跑 `verify` 及本機整合測試。使用 VM 時，客體重開機與實體主機重開機是不同項目；不得混稱。確認主機 UUID／SSH host key 是新生成的，沒有繼承來源設備身分。

重跑安裝器後比對設備密碼、資料庫與應用內容仍在。安裝器是新機建置／續跑工具，不是任意既有設備的升級工具；遇到版本不符或現有部署碰撞應停止並調查。

## 網路與尚待授權項目

正式實體新機使用自己的區網 IPv4。驗收 VM 若採 NAT，管理頁的單一轉送埠不代表每個應用埠或 Pi Web ingress 都已對外轉送；完整網頁測試可使用 SSH SOCKS 代理進入客體網路。跨網域／外部 HTTPS／PWA 安裝須在新設備完成 Cloudflare／PaaS 授權後另行驗收。

模型供應商登入、VPN 節點、ngrok、外部 Kubernetes 與個別 MCP 後端設定屬於新設備的設定範圍。來源設備的登入狀態、Tunnel、使用者工作流程、檔案與 Matter fabric 都不會複製。

九個額外 MCP 管理服務的首次測試涵蓋管理頁、登入、錯誤權杖拒絕及服務狀態；尚未設定後端的產品會明確回報 `not_configured`／`missing`。這不能當成已透過九個 MCP 操作實際業務系統的證明。本發行版另外自動連接並實測的是 HA MCP。
