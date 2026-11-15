# 既有設備維護：ML、Nextcloud 結構與備份導覽

2026-11-15 實測完成：Immich ML 健康檢查與 512 維推論通過；Nextcloud 35.0.3 官方結構檢查零差異，Text／Office 編輯儲存及下載回讀通過；Cockpit 備份頁已移到工具分類的應用軟體下方，桌面與手機驗收通過。原資料、帳號與網址保留。

本紀錄補充 `2026.11.15-rc1` 的實體設備驗收。版本與映像見
[`maintenance.json`](../releases/2026.11.15-rc1/maintenance.json)，實際結果見同目錄的
[公開驗收證據](../releases/2026.11.15-rc1/evidence/physical-closeout.json)。歷史 rc1 tag、37 個新機映像與原始材料索引不改寫；
下列 Nextcloud 35.0.3 是既有設備的維護例外，不代表新機安裝器自動升至該版。

## 原設備 Immich ML

原有 Immich 2.7.5 的 Gunicorn 25.1.0 master／worker 卡住，`/ping` 逾時；
不是模型供應商登入問題。採用 [Immich 上游 #27228](https://github.com/immich-app/immich/issues/27228)
所列的 control socket 停用方式，保留原映像及全部掛載。

`overlays/immich-ml-gunicorn.conf` 是給原本已有此服務的設備使用，不會把 Immich
加入新機方案。先確認 Gunicorn 版本及既有 `GUNICORN_CMD_ARGS`；若已有自訂參數，
須合併審查，不能直接覆寫。備份原 Quadlet 後，把檔案裝到：

```text
~/.config/containers/systemd/immich-machine-learning.container.d/90-woow-gunicorn-control.conf
```

執行使用者的 `systemctl --user daemon-reload`，只重啟
`immich-machine-learning.service`。驗收包含容器健康、server 到 ML 的 HTTP 連線，
及 `/predict` 的 `ViT-B-32__openai` 文字推論：結果必須是 512 個有限數值且非全零。
模型首次下載可花數十秒，不把這個等待當作卡死。此測試不讀取使用者相片。

回退方式是撤回這次新增的 drop-in、重新載入並重啟 ML；不移除資料卷或模型快取。

## Nextcloud 35.0.1 → 35.0.3

原先 `taskp_tasks_scheduled`、`text_steps_doc_id_id_index` 都是官方程式使用的效能索引。
35.0.3 的官方檢查器承認選用索引，因此保留兩者，以官方維護版修正檢查差異；
不修改 Core 原始碼、不關閉檢查，也不刪除這兩個索引。

此次另遇到分享應用的升級遺留：
[`52a07c0`](https://github.com/nextcloud/server/commit/52a07c0b16ec1dd622003af9c4cbbb3429c64e08)
從官方初始 migration 移除三欄唯一索引，但原設備仍保留該索引。
35.0.3 的 `db:schema:expected` 不再包含它。它與前述兩個效能索引是不同項目。

`installer/repair-nextcloud-sharing-index.py` 只處理這個已審查情境，預設預覽：

```bash
python3 distribution/installer/repair-nextcloud-sharing-index.py \
  --app nextcloud-app --db nextcloud-db --backup /private/full-cold-backup
# 審查預覽、完成隔離升級與回退後，才加上 --apply。
```

必要條件：Nextcloud 35.0.3、Sharing 1.0.5、`oc_` 表前綴、分享收件者表完全為空、
官方檢查只有指定的一項差異、唯一索引定義完全吻合，而且它不被任何 constraint 使用。
執行前校驗完整 HTML、資料、設定、資料庫及角色備份；保存重建索引的 SQL。
交易內取得表鎖，再次確認零資料列及約束，僅移除該舊索引，沒有 `CASCADE`。
其他索引、主鍵、外鍵逐項比對，最後以未修改的官方 `db:schema:check` 驗證。
任一條件不符就停止；這不是可對所有設備自動執行的通用清理器。

維護程序先在無對外連接埠、無網路出口的副本升級及還原，再取得正式服務的最終完整
冷備份，切換固定映像。原帳號、密碼雜湊、instance secret、設定、掛載與網址須逐項保留。
失敗時恢復同一份 HTML＋資料庫＋檔案備份及舊 Quadlet；Nextcloud 不支援只換舊映像降版。

冷備份的恢復程序可能單獨啟動成員、而 target 仍是 inactive。切換映像時不能只停用
target 或只執行 start：須明確停止 app、gateway、Office、DB、Redis 與 cron，再載入
新的 Quadlet 並啟動群組。啟動後先核對實際容器 image config ID，不能由已修改的
`Image=` 或容器顯示 healthy 推論新版本已經運行。本次實測曾因舊 app 仍運行而停在
版本等待，明確重啟 app 後才進入官方升級；沒有跳過版本檢查。原有維護模式也會由官方升級保留，準備狀態應以新版號及 `needsDbUpgrade=false` 判定，再於檢查完成後關閉維護模式。正式切換、備份與驗證合計 468.9 秒，不是精確 HTTP 停機時間。

更新後須另外測試 Text 開啟／編輯／WebDAV 讀回，以及 Collabora DOCX 編輯／儲存／下載
解析內容；測試帳號及檔案最後清除。此設備原有一位使用者、零個使用者檔案，不能由此
推論大量業務資料遷移或所有分享類型都完成驗收。

## Cockpit 備份導覽

同步 [Woow_cockpit PR #15](https://github.com/WOOWTECH/Woow_cockpit/pull/15)，來源 commit
`c393dfbc79eacd26224c3f42e2d0d8b41de2f2f5`。備份頁由系統分類移至工具，順序 41，
緊接順序 40 的「應用軟體」。原 `/woowtechbackup` 路徑、備份引擎、金鑰與應用設定保留。

既有設備使用 Cockpit 來源的正式 `manage.py` 計畫、安裝及驗證流程；本次只有備份
manifest 與安裝紀錄變更。新機配方的 `patch-cockpit-backup-navigation.py` 對歷史固定
來源套用相同導覽，遇到未知 manifest 結構會停止，已套用來源可重複執行。

瀏覽器驗收須在 1440px 與 390px 確認工具／系統分類、順序、六個分頁、24 個應用設定
及水平溢出；僅驗收導覽與既有內容讀取，不將其表述為重新完成全部 24 個應用跨機還原。
