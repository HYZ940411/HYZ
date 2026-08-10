# GSC API 抓取工具

取代手動匯出 CSV。解決介面匯出的三個限制：查詢與頁面無法對應、查詢被截在 1,000 列、
查詢沒有日期維度。

## 一次性設定

1. **Google Cloud Console** → 建立專案（或用既有的）→
   「API 和服務」→「程式庫」→ 搜尋 **Google Search Console API** → 啟用。

2. **OAuth 同意畫面** → 使用者類型選「外部」→ 填應用程式名稱與聯絡信箱 →
   **在「測試使用者」把自己的 Google 帳號加進去**（不加會在授權時被擋）。
   發布狀態維持「測試」即可，不需要送審。

3. **建立憑證** →「OAuth 用戶端 ID」→ 應用程式類型選 **桌面應用程式** →
   建立後下載 JSON。

4. 把 JSON 放到 `~/.config/gsc/client_secret.json`：

   ```bash
   mkdir -p ~/.config/gsc
   mv ~/Downloads/client_secret_*.json ~/.config/gsc/client_secret.json
   ```

5. 跑一次授權（會開瀏覽器，選帳號 → 同意）：

   ```bash
   python3 tools/gsc_auth.py
   ```

   憑證寫進 `~/.config/gsc/token.json`，之後不用再授權。
   使用的帳號必須在該 GSC 資源有權限。

## 用法

```bash
# 確認抓得到哪些站台
python3 tools/gsc_fetch.py --list

# 抓單一期間
python3 tools/gsc_fetch.py --site https://roaming-taiwan.com/ \
    --start 2026-05-03 --end 2026-08-02 \
    --out "允諾 SEO/旅遊包租車/API_2026-05-03_2026-08-02"

# 連前一期一起抓（等長區間，輸出到 <out>_前期）
python3 tools/gsc_fetch.py --site ... --start ... --end ... --prev --out ...

# 另外抓 日期×查詢（做關鍵字逐日趨勢用，列數會很大）
python3 tools/gsc_fetch.py --site ... --start ... --end ... --daily-query --out ...
```

`--site` 要與 GSC 裡的資源型態一致：網址前置字元資源用 `https://example.com/`，
網域資源用 `sc-domain:example.com`。用 `--list` 看實際字串最保險。

## 輸出

| 檔案 | 維度 | 說明 |
|---|---|---|
| `圖表.csv` | 日期 | 與介面匯出相同 |
| `查詢.csv` | 查詢 | 上限 25,000 列並自動分頁，遠多於介面的 1,000 |
| `網頁.csv` | 頁面 | 與介面匯出相同 |
| `網頁_查詢.csv` | 頁面 × 查詢 | **介面匯出拿不到**，每篇文章實際排上哪些字 |
| `國家_地區.csv`、`裝置.csv` | — | 與介面匯出相同 |
| `每日查詢.csv` | 日期 × 查詢 | 只有加 `--daily-query` 才產 |

## 仍然存在的限制

- **GSC 隱私門檻**：過於稀有的查詢 API 一樣不提供，查詢層級的點擊總和永遠小於
  圖表檔。腳本會在抓完後印出涵蓋率，報告裡要照實揭露。
- **資料保留 16 個月**，更早的期間抓不到。
- **最近 1–3 天資料未統整完成**，做趨勢圖時要排除。

## 憑證安全

`~/.config/gsc/` 在 repo 之外，不會被 git 追蹤。`.gitignore` 另外擋掉
`client_secret*.json`、`token.json` 以防誤放進專案目錄。
