"""
Worked example of the GSC growth-comparison computations.

NOTE: this is a reusable TEMPLATE assembled from computations that were run
piecemeal during a real project — the individual formulas are proven, but this
combined file has not itself been executed end-to-end. Treat it as a starting
point to adapt and verify against your own data, not as a turnkey script.

This is a STARTING POINT, not a black box. Column names, file paths, the
priority-URL list, and the period boundary all change per project — edit them.

The three GSC exports have no shared key, so we work each dimension separately:
  - Chart file  -> daily totals (for overall growth + weekly trend)
  - Pages file  -> per-URL metrics (for priority-article breakdown)
  - Queries file-> per-keyword (topical inference only; no page mapping)

Key ideas demonstrated:
  1. Normalizing the CTR string column.
  2. Verifying a newer export is cumulative (overlap identical to old export).
  3. Diffing to get the *incremental* new window when the file is cumulative.
  4. Comparing per-DAY averages when the two windows differ in length.
  5. Weekly rollups for the trend chart, tagging prior vs current period.
  6. Reconstructing a page's position for the new window via the
     impression-weighted identity.
"""

import pandas as pd


# ---- 0. Helpers -------------------------------------------------------------

def load(path):
    """Load a GSC CSV and normalize the CTR column regardless of header language."""
    df = pd.read_csv(path)
    ctr_col = '點閱率' if '點閱率' in df.columns else 'CTR'
    df['ctr'] = df[ctr_col].astype(str).str.rstrip('%').astype(float)
    return df


def col(df, *candidates):
    """Return the first matching column name (handles zh/en headers)."""
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"none of {candidates} in {list(df.columns)}")


# ---- 1. Load ----------------------------------------------------------------

# EDIT THESE PATHS. GSC exports are usually named 圖表/Chart (daily),
# 網頁/Pages, 查詢/Queries. For a growth comparison you need the previous
# export AND the newer (often cumulative) one.
chart_old = load('舊_圖表.csv')     # previous export's daily file (optional)
chart_new = load('新_圖表.csv')     # newer daily file (may be cumulative)
pages_old = load('舊_網頁.csv')
pages_new = load('新_網頁.csv')

DATE = col(chart_new, '日期', 'Date')
CLICKS = col(chart_new, '點擊', 'Clicks')
IMPR = col(chart_new, '曝光', 'Impressions')
POS = col(chart_new, '排名', 'Position')
URL = col(pages_new, '熱門網頁', 'Top pages', 'Page')

for c in (chart_old, chart_new):
    c[DATE] = pd.to_datetime(c[DATE])

# EDIT THIS — the boundary between "previous" and "new" window
PERIOD_SPLIT = pd.Timestamp('2026-06-22')   # first day of the NEW window


# ---- 2. Verify the newer export is cumulative -------------------------------
# If the new file simply extends the old one from the same start date, the
# overlapping days must match exactly. If they do, we can diff safely.

if chart_old is not None:
    m = chart_old.merge(chart_new, on=DATE, suffixes=('_old', '_new'))
    mismatch = m[(m[f'{CLICKS}_old'] != m[f'{CLICKS}_new']) |
                 (m[f'{IMPR}_old'] != m[f'{IMPR}_new'])]
    print(f"overlap days: {len(m)}  mismatched: {len(mismatch)}")
    assert len(mismatch) == 0, "overlap differs — export is NOT a clean cumulative extension"


# ---- 3. Split into prior vs new window, compare per-DAY ----------------------

p1 = chart_new[chart_new[DATE] < PERIOD_SPLIT]      # previous window
p2 = chart_new[chart_new[DATE] >= PERIOD_SPLIT]     # new window


def per_day(d):
    n = len(d)
    return {
        'days': n,
        'clicks_total': int(d[CLICKS].sum()),
        'impr_total': int(d[IMPR].sum()),
        'clicks_per_day': round(d[CLICKS].sum() / n, 2),
        'impr_per_day': round(d[IMPR].sum() / n, 1),
        'ctr': round(d[CLICKS].sum() / d[IMPR].sum() * 100, 2),
        'position': round(d[POS].mean(), 2),   # simple daily mean is fine for overall
    }


s1, s2 = per_day(p1), per_day(p2)
growth = lambda a, b: round((b / a - 1) * 100) if a else None
print("\nprev :", s1)
print("new  :", s2)
print("clicks/day growth:", growth(s1['clicks_per_day'], s2['clicks_per_day']), "%")
print("impr/day  growth:", growth(s1['impr_per_day'], s2['impr_per_day']), "%")
print("position:", s1['position'], "->", s2['position'],
      "(lower = better; +", round(s1['position'] - s2['position'], 2), "improvement)")


# ---- 4. Weekly rollups for the trend chart ----------------------------------
# Tag each week as prior ('p1') or current ('p2') so the chart can color them.

w = (chart_new
     .groupby(chart_new[DATE].dt.to_period('W').apply(lambda r: r.start_time))
     .agg(clicks=(CLICKS, 'sum'), impressions=(IMPR, 'sum'), rank=(POS, 'mean'))
     .reset_index())
w.columns = ['week_start', 'clicks', 'impressions', 'rank']
w['label'] = w['week_start'].dt.strftime('%m/%d')
w['period'] = w['week_start'].apply(lambda d: 'p1' if d < PERIOD_SPLIT else 'p2')
w['rank'] = w['rank'].round(2)

# IMPORTANT: drop the final partial week if the export's last day is not a full
# week / not yet finalized by GSC. Example — exclude the last label:
LAST_PARTIAL = w['label'].iloc[-1]   # inspect and decide; often the trailing week
weekly = w[w['label'] != LAST_PARTIAL]
weekly[['label', 'clicks', 'impressions', 'rank', 'period']].to_json(
    'weekly.json', orient='records', force_ascii=False)


# ---- 5. Per-priority-page comparison ----------------------------------------
# EDIT THIS list. Titles are best fetched live (see SKILL.md).

PRIORITY = [
    # (url, title, category)
    ("https://example.com/2026/05/15/guide/", "My Guide Title", "指南"),
]


def get(df, url, c):
    m = df[df[URL] == url]
    return float(m.iloc[0][c]) if len(m) else 0.0


rows = []
for url, title, cat in PRIORITY:
    oc, ic, op = get(pages_old, url, CLICKS), get(pages_old, url, IMPR), get(pages_old, url, POS)
    tc, ti, tp = get(pages_new, url, CLICKS), get(pages_new, url, IMPR), get(pages_new, url, POS)
    # incremental new-window values (cumulative export → subtract)
    dc, di = tc - oc, ti - ic
    # reconstruct new-window position via impression-weighted identity
    p2_pos = round((tp * ti - op * ic) / di, 2) if di > 0 else None
    d1 = oc / s1['days']           # prev clicks/day
    d2 = dc / s2['days']           # new  clicks/day
    rows.append({
        'url': url, 'title': title, 'category': cat,
        'p1_clicks': int(oc), 'p2_clicks': int(dc),
        'p1_impr': int(ic), 'p2_impr': int(di),
        'p1_pos': round(op, 2), 'p2_pos': p2_pos,
        'pos_up': (op > p2_pos) if p2_pos is not None else None,  # True = improved
        'p1_cpd': round(d1, 2), 'p2_cpd': round(d2, 2),
        'growth': growth(d1, d2) if d1 > 0 else None,             # None => grew from 0
    })

rows.sort(key=lambda r: -r['p2_clicks'])
pd.Series(rows).to_json('targets.json', orient='values', force_ascii=False)
for r in rows:
    print(f"{r['category']:<10} clicks {r['p1_clicks']}->{r['p2_clicks']}  "
          f"pos {r['p1_pos']}->{r['p2_pos']}  growth {r['growth']}")