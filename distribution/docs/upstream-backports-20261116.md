# 部署問題回推各來源 main：2026-11-16

本次新增 **11 個來源倉庫**的修正 PR，全部於 CI 通過後合併。另核對既有
Cockpit、Nextcloud 備份與 Pi plugin 修正確實包含於各自 main。
完整 SHA、受測 PR head、CI 連結及查核時間見
[GitHub main 查核證據](evidence/upstream-main-20261116.json)。

## 本次新增來源修正

| 倉庫／PR | main 合併提交 | 修正內容 |
|---|---|---|
| [Woow_native_os_pi_agent #14](https://github.com/WOOWTECH/Woow_native_os_pi_agent/pull/14) | [`9180029`](https://github.com/WOOWTECH/Woow_native_os_pi_agent/commit/91800299ca6b5f408746ddf59e02b8f7b8645262) | 採用已發布的 Omnigent plugin 0.3.32；重新驗證 native 修補，增加已授權本機連線的冷啟動恢復服務。 |
| [Woow_podman_code_server_package #26](https://github.com/WOOWTECH/Woow_podman_code_server_package/pull/26) | [`89e6648`](https://github.com/WOOWTECH/Woow_podman_code_server_package/commit/89e6648c023fa569b37b5bef8442c3acdb91c5f7) | keep-id 首次映像權限複製的啟動期限延長至 900 秒。 |
| [Woow_podman_emqx #10](https://github.com/WOOWTECH/Woow_podman_emqx/pull/10) | [`37db768`](https://github.com/WOOWTECH/Woow_podman_emqx/commit/37db768f121eecd795002e79230bad24fa61d086) | 用本機 HTTP status 取代昂貴 Erlang CLI 健康檢查；HA discovery 改成指定帳號的選用 ACL，不開放所有帳號。 |
| [Woow_podman_hermes #16](https://github.com/WOOWTECH/Woow_podman_hermes/pull/16) | [`3ac874c`](https://github.com/WOOWTECH/Woow_podman_hermes/commit/3ac874c027c89bf5e4e712c6c575c291ae824978) | 併行冷啟動時，provision 等待 gateway 的期限由 300 延長至 900 秒。 |
| [Woow_podman_homeassistant #8](https://github.com/WOOWTECH/Woow_podman_homeassistant/pull/8) | [`5dc8018`](https://github.com/WOOWTECH/Woow_podman_homeassistant/commit/5dc80184662edc30e1d4841728d7429e439efe32) | 升級及選用 existing seed 模式保留本機設定，整組保留相同／較新／無法辨認版本的自訂整合，記錄保留策略。 |
| [Woow_podman_immich #7](https://github.com/WOOWTECH/Woow_podman_immich/pull/7) | [`8a48e65`](https://github.com/WOOWTECH/Woow_podman_immich/commit/8a48e653ca52b0b8972a588cead758371144cd65) | 提供 ML Gunicorn control-socket 停用設定與既有環境維護方式；不刪模型快取，不更動原照片。 |
| [Woow_podman_litellm #7](https://github.com/WOOWTECH/Woow_podman_litellm/pull/7) | [`b088f1f`](https://github.com/WOOWTECH/Woow_podman_litellm/commit/b088f1f140b47d229741460e4a6538d69a9e6918) | 初次 Prisma 初始化不再被主動健康檢查的重試次數提早終止；保留安裝期限及正常健康檢查。 |
| [Woow_podman_nextcloud #9](https://github.com/WOOWTECH/Woow_podman_nextcloud/pull/9) | [`ca9fc79`](https://github.com/WOOWTECH/Woow_podman_nextcloud/commit/ca9fc79942c10ec80bec5a514ccada30a7a3bdb1) | 35.0.3 來源版本與 34.0.6 中繼閘、初始化後才執行 cron、選用 Office／gateway 群組及備份設定、明確啟用的相容性修復工具。 |
| [Woow_podman_odoo #10](https://github.com/WOOWTECH/Woow_podman_odoo/pull/10) | [`138d10c`](https://github.com/WOOWTECH/Woow_podman_odoo/commit/138d10cd2d763a03ca52269771651667035c147f) | 首次初始化 tenant 後正確標記新資料庫，以 fresh adoption 通過升級閘；既有資料庫不重新初始化。 |
| [Woow_podman_omnigent_package #14](https://github.com/WOOWTECH/Woow_podman_omnigent_package/pull/14) | [`4317598`](https://github.com/WOOWTECH/Woow_podman_omnigent_package/commit/431759826c6e6ea25579b05051de102699e54229) | keep-id 首次映像權限複製的啟動期限延長至 900 秒。 |
| [Woow_podman_opendesign #16](https://github.com/WOOWTECH/Woow_podman_opendesign/pull/16) | [`c19af6c`](https://github.com/WOOWTECH/Woow_podman_opendesign/commit/c19af6cc1323e4f3d1dd9ee9bb494a4779c42332) | keep-id 冷啟動等待延長；重建共用 namespace 主容器前移除已停止的三個附屬容器，保留資料卷。 |

## 已先行合併的修正

- [Woow_cockpit #13](https://github.com/WOOWTECH/Woow_cockpit/pull/13)：Fix branding installation on version-held Cockpit packages；main 包含 `98647b0`。
- [Woow_cockpit #14](https://github.com/WOOWTECH/Woow_cockpit/pull/14)：Support Pi ingress on userspace VPNs while preserving browser URLs；main 包含 `73aef7a`。
- [Woow_cockpit #15](https://github.com/WOOWTECH/Woow_cockpit/pull/15)：「備份與還原」移到「工具」群組，放在「應用軟體」下面；main 包含 `c393dfb`。
- [Woow_podman_nextcloud #8](https://github.com/WOOWTECH/Woow_podman_nextcloud/pull/8)：Preserve config in backups of rootless UID-owned deployments；main 包含 `3da3618`。
- [pi-omnigent-plugin #29](https://github.com/WOOWTECH/pi-omnigent-plugin/pull/29)：慢的板子開機後不再把已裝的 Omnigent 當成沒裝：版本查詢與拿鎖改等 30 秒；main 包含 `3a58bb4`。
- [pi-omnigent-plugin #30](https://github.com/WOOWTECH/pi-omnigent-plugin/pull/30)：Release v0.3.32：慢的板子開機後不再把已裝的 Omnigent 當成沒裝；main 包含 `2bfdd7d`。

Pi plugin 的 30 秒偵測修正已由上游 PR #29 與 0.3.32 發布 PR #30 完成；本次
由 Native Pi 採用官方版本，沒有另做重複插件修改。

## 保留在整機倉庫的內容

`user@.service` 停機期限、needrestart 排除規則、跨應用啟動順序、內容雜湊、
映像轉運與整機驗收是平台層責任，仍由此倉庫維護。沒有把主機帳號、密碼、
Token、工作流程、檔案資料、模型授權或私人對外網址寫入來源倉庫。

`v2026.11.15-rc1` tag、來源鎖與既有實體驗收紀錄**不改寫**。該版本使用較早
的固定來源加已記錄的 overlays；來源 main 現在包含通用修正，並不表示歷史
rc1 已偷偷改用最新版。Nextcloud standalone main 的預設是 35.0.3，rc1 新機
仍維持原鎖定內容；既有設備的 35.0.3 維護例外繼續另行記錄。
下一個整機版本須重新鎖定這批提交、建置材料並完成自己的新機驗收，不能直接
把舊驗收證據標成新版。這次回推沒有再更動客戶服務、資料或網址。

## 驗證與限制

- 各新增 PR 的必要 CI 成功；預期不適用的發布作業可能為 skipped。
- Odoo 首次 tenant 初始化回歸、EMQX 選用 ACL 隔離、HA 29 項腳本情境與
  自訂整合保留測試、各專案 Quadlet/systemd 檢查通過。
- Native Pi 的六種連線恢復邊界與既有 native 修補／啟動器測試通過。
  官方插件 installer/resume 63 項通過；鎖測試在並行負載下曾遇到既有的
  排程敏感 assertion，隔離重跑七項通過。這不等於已消除該測試的偶發性。
- Nextcloud Office／備份配置／中繼版實際 render、版本閘、八項 archive/schema
  CLI 測試、rootless 備份、14 項回退模型及六項版本讀取測試通過。
  Sharing schema 修改的版本、空表、完整備份檢查在 `python -O` 下仍有效。
- [實體重開機](reboot-acceptance.md)與[功能收尾](maintenance-closeout.md)證據
  適用先前實際部署的版本及 overlays。本次沒有把來源測試冒稱為再次實體重啟、
  所有 macOS 硬體驗收或全套跨機還原驗收。
