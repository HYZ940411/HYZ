#!/usr/bin/env python3
"""從 Search Console API 抓成效資料，輸出成 CSV。

授權請先跑 tools/gsc_auth.py。

範例：
    # 列出這個帳號有權限的所有站台
    python3 tools/gsc_fetch.py --list

    # 抓單一期間（欄位與 GSC 介面匯出的中文檔一致，另加 page×query）
    python3 tools/gsc_fetch.py --site https://roaming-taiwan.com/ \\
        --start 2026-05-03 --end 2026-08-02 \\
        --out "允諾 SEO/旅遊包租車/API_2026-05-03_2026-08-02"

    # 同時抓前一期，方便做期間對比
    python3 tools/gsc_fetch.py --site https://roaming-taiwan.com/ \\
        --start 2026-05-03 --end 2026-08-02 --prev \\
        --out "允諾 SEO/旅遊包租車/API_2026-05-03_2026-08-02"

輸出檔案：
    圖表.csv          日期 × 點擊/曝光/點閱率/排名
    查詢.csv          查詢字（API 上限 25,000 列，遠多於介面的 1,000）
    網頁.csv          頁面
    網頁_查詢.csv     頁面 × 查詢 —— 介面匯出拿不到的對應關係
    國家_地區.csv / 裝置.csv / 每日查詢.csv（--daily-query 時才產）

注意：GSC 會隱去過於稀有的查詢（隱私門檻），API 一樣拿不到，
所以查詢層級的點擊總和仍會小於圖表檔。這是 Google 端的限制。
"""
import argparse
import csv
import datetime
import os
import pathlib
import sys
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
CONF = pathlib.Path(os.environ.get("GSC_CONFIG_DIR", pathlib.Path.home() / ".config" / "gsc"))
TOKEN = CONF / "token.json"
ROW_LIMIT = 25000

# 輸出檔名 → API 維度組合
PRESETS = {
    "圖表.csv": ["date"],
    "查詢.csv": ["query"],
    "網頁.csv": ["page"],
    "網頁_查詢.csv": ["page", "query"],
    "國家_地區.csv": ["country"],
    "裝置.csv": ["device"],
}
DIM_HEADER = {
    "date": "日期", "query": "查詢", "page": "網頁",
    "country": "國家/地區", "device": "裝置", "searchAppearance": "搜尋外觀",
}


def service():
    if not TOKEN.exists():
        sys.exit(f"找不到憑證 {TOKEN}，請先執行：python3 tools/gsc_auth.py")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
        else:
            sys.exit("憑證已失效，請重新執行：python3 tools/gsc_auth.py")
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def query_all(svc, site, start, end, dimensions, search_type="web"):
    """分頁抓完所有列。API 單次上限 25,000 列。"""
    rows, start_row = [], 0
    while True:
        body = {
            "startDate": start, "endDate": end,
            "dimensions": dimensions,
            "type": search_type,
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
        }
        for attempt in range(5):
            try:
                resp = svc.searchanalytics().query(siteUrl=site, body=body).execute()
                break
            except HttpError as e:
                if e.resp.status in (429, 500, 503) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise
        batch = resp.get("rows", [])
        rows.extend(batch)
        if len(batch) < ROW_LIMIT:
            return rows
        start_row += ROW_LIMIT


def write_csv(path, dimensions, rows):
    header = [DIM_HEADER.get(d, d) for d in dimensions] + ["點擊", "曝光", "點閱率", "排名"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            keys = r.get("keys", [])
            w.writerow(keys + [
                r.get("clicks", 0),
                r.get("impressions", 0),
                f"{r.get('ctr', 0) * 100:.2f}%",
                f"{r.get('position', 0):.2f}",
            ])
    return len(rows)


def fetch_period(svc, site, start, end, outdir, daily_query=False):
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    presets = dict(PRESETS)
    if daily_query:
        presets["每日查詢.csv"] = ["date", "query"]
    summary = []
    for name, dims in presets.items():
        rows = query_all(svc, site, start, end, dims)
        n = write_csv(outdir / name, dims, rows)
        clicks = sum(r.get("clicks", 0) for r in rows)
        impr = sum(r.get("impressions", 0) for r in rows)
        summary.append((name, n, clicks, impr))
        print(f"  {name:16s} {n:6,} 列   點擊 {clicks:>7,}   曝光 {impr:>9,}")
    # 覆蓋率：查詢層級 ÷ 日期層級，報告裡要揭露
    by = {s[0]: s for s in summary}
    if "圖表.csv" in by and "查詢.csv" in by:
        tot, q = by["圖表.csv"][2], by["查詢.csv"][2]
        if tot:
            print(f"  → 查詢層級涵蓋 {q / tot * 100:.1f}% 的點擊（其餘為 GSC 隱去的稀有查詢）")
    return summary


def prev_period(start, end):
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    days = (e - s).days + 1
    pe = s - datetime.timedelta(days=1)
    ps = pe - datetime.timedelta(days=days - 1)
    return ps.isoformat(), pe.isoformat()


def main():
    ap = argparse.ArgumentParser(description="從 Search Console API 抓成效資料")
    ap.add_argument("--list", action="store_true", help="列出有權限的站台後結束")
    ap.add_argument("--site", help="站台網址，例如 https://roaming-taiwan.com/ 或 sc-domain:example.com")
    ap.add_argument("--start", help="起始日 YYYY-MM-DD")
    ap.add_argument("--end", help="結束日 YYYY-MM-DD")
    ap.add_argument("--out", help="輸出資料夾")
    ap.add_argument("--prev", action="store_true", help="同時抓等長的前一期，輸出到 <out>_前期")
    ap.add_argument("--daily-query", action="store_true",
                    help="另外抓 日期×查詢（列數很大，但這是唯一能做關鍵字逐日趨勢的方式）")
    args = ap.parse_args()

    svc = service()

    if args.list:
        for s in svc.sites().list().execute().get("siteEntry", []):
            print(f"{s['permissionLevel']:22s} {s['siteUrl']}")
        return

    missing = [f for f in ("site", "start", "end", "out") if not getattr(args, f)]
    if missing:
        sys.exit(f"缺少參數：{'、'.join('--' + m for m in missing)}（或用 --list 看站台清單）")

    print(f"站台 {args.site}")
    print(f"期間 {args.start} – {args.end}")
    fetch_period(svc, args.site, args.start, args.end, args.out, args.daily_query)

    if args.prev:
        ps, pe = prev_period(args.start, args.end)
        print(f"前期 {ps} – {pe}")
        fetch_period(svc, args.site, ps, pe, f"{args.out}_前期", args.daily_query)


if __name__ == "__main__":
    main()
