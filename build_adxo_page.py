# -*- coding: utf-8 -*-
"""
DXペディション予定（3か月以内）のWebページを作る（GitHub Actionsで1日2回実行）
出典: NG3K Announced DX Operations テキスト版 https://www.ng3k.com/Misc/adxoplain.html
使い方: python build_adxo_page.py               … ADXOを取得して docs/index.html を作る
        python build_adxo_page.py 保存したファイル.html … 保存したテキスト版から作る（試験用）
標準ライブラリだけで動きます。
"""
import html, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

ADXO_URL = "https://www.ng3k.com/Misc/adxoplain.html"
ADXO_TABLE = "https://www.ng3k.com/Misc/adxo.html"
HOME = "https://ja1bbe.wixsite.com/mysite"
DAYS = 92                                   # 約3か月先まで
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
BANDS = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]
HF = ["80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]   # HFは3〜30MHz。160m（1.8MHz）は含めない
MODES = ["CW", "SSB", "FT8", "FT4", "RTTY", "SSTV", "PSK"]


def fetch():
    req = urllib.request.Request(ADXO_URL, headers={"User-Agent": "JA1BBE DXpedition page (GitHub Actions, twice a day)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse(text):
    out = []
    dpat = re.compile(r"(\w{3}) (\d+)(?:, (\d{4}))?-(?:(\w{3}) )?(\d+), (\d{4})$|(\w{3}) (\d+), (\d{4})$")
    clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()
    for head, body in re.findall(r"<p>\s*([^<\n]+?)\s*<br>\s*DXCC:(.*?)</p>", text, re.S):
        m = dpat.match(head.strip())
        if not m:
            continue
        try:
            if m.group(7):
                start = end = date(int(m.group(9)), MON[m.group(7)], int(m.group(8)))
            else:
                m1, d1, y1, m2, d2, y2 = m.group(1, 2, 3, 4, 5, 6)
                y2 = int(y2)
                mo2 = MON[m2] if m2 else MON[m1]
                y1 = int(y1) if y1 else (y2 - 1 if MON[m1] > mo2 else y2)
                start, end = date(y1, MON[m1], int(d1)), date(y2, mo2, int(d2))
        except (KeyError, ValueError):
            continue
        parts = {}
        for seg in re.split(r"<br>", "DXCC:" + body):
            k, _, v = seg.partition(":")
            parts[k.strip()] = v
        cs = parts.get("Callsign", "")
        url = re.search(r'href="([^"]+)"', cs)
        info = clean(parts.get("Info", ""))
        out.append({"start": start, "end": end, "entity": clean(parts.get("DXCC", "")),
                    "call": clean(cs), "url": url.group(1) if url else None,
                    "qsl": clean(parts.get("QSL", "")), "info": info,
                    "bands": bands_of(info), "modes": modes_of(info)})
    return out


def bands_of(info):
    """Info の「80-10m」「160-6m」「HF + 6m」「incl 60m」などから運用バンドを推定する（推定できなければ空）"""
    s = info.replace("–", "-")
    found = set()
    for a, b in re.findall(r"\b(160|80|60|40|30|20|17|15|12|10|6)\s*-\s*(160|80|60|40|30|20|17|15|12|10|6)\s*m\b", s):
        i, j = BANDS.index(a + "m"), BANDS.index(b + "m")
        rng = BANDS[min(i, j):max(i, j) + 1]
        found |= {x for x in rng if x != "60m"}          # 範囲表記に60mは含めない（明記されたときだけ）
    for x in re.findall(r"\b(160|80|60|40|30|20|17|15|12|10|6)\s*m\b", s):
        found.add(x + "m")
    if re.search(r"\bHF\b", s):
        found |= set(HF)
    return [b for b in BANDS if b in found]


def modes_of(info):
    s = info.upper()
    found = [m for m in MODES if re.search(r"\b" + m + r"\b", s)]
    if "DIGITAL" in s and not any(m in found for m in ("FT8", "FT4", "RTTY", "PSK")):
        found.append("DIGI")
    return found


def render(ops, today, updated):
    rows = []
    for o in ops:
        now = o["start"] <= today <= o["end"]
        left = (o["end"] - today).days
        mon = lambda x: f'{x:%b} {x.day}' + (f', {x.year}' if o["start"].year != o["end"].year else "")
        d = f'{mon(o["start"])} – {mon(o["end"])}'          # 月を英語の略称にして、日付の順番の誤解を防ぐ
        until = (o["start"] - today).days
        en = lambda n, w: f'{n} {w}' + ("" if n == 1 else "s")
        state = (f'<span class="badge now">運用中 Active</span><span class="left">残り{left}日 / {en(left, "day")} left</span>'
                 if now else f'<span class="left">{until}日後から / starts in {en(until, "day")}</span>')
        call = html.escape(o["call"])
        link = o["url"] or f'https://www.qrz.com/db/{o["call"]}'
        chips = "".join(f'<span class="chip">{b}</span>' for b in o["bands"])
        chips += "".join(f'<span class="chip mode">{m}</span>' for m in o["modes"])
        rows.append(
            f'<article class="op" data-now="{int(now)}" data-bands="{" ".join(o["bands"])}" '
            f'data-modes="{" ".join(o["modes"])}">'
            f'<div class="meta">{d}　{state}</div>'
            f'<h2>{html.escape(o["entity"])} <a href="{html.escape(link)}" target="_blank" rel="noopener">{call}</a></h2>'
            f'<div class="chips">{chips}</div>'
            f'<p class="info">{html.escape(o["info"])}</p>'
            f'<div class="qsl">QSL: {html.escape(o["qsl"] or "—")}</div></article>')
    bands_btn = "".join(f'<button data-band="{b}">{b}</button>' for b in BANDS)
    modes_btn = "".join(f'<button data-mode="{m}">{m}</button>' for m in ["CW", "SSB", "FT8", "FT4", "RTTY"])
    n_now = sum(1 for o in ops if o["start"] <= today <= o["end"])
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DXペディション予定 / DXpeditions — next 3 months | JA1BBE</title>
<style>
:root {{ --ink:#1C2430; --sub:#5A6573; --rule:#D5DAE1; --paper:#FFFFFF; --tint:#F3F5F8;
        --good:#1F7A4D; --navy:#24476B; --chip:#E9EEF4; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --ink:#E8ECF1; --sub:#A3ADBA; --rule:#2E3846; --paper:#161C24; --tint:#0E1319;
          --good:#3FA672; --navy:#8FB4DA; --chip:#232C38; color-scheme: dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--tint); color:var(--ink);
       font-family:-apple-system,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP",Meiryo,sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding:16px 12px 40px; }}
header {{ background:var(--navy); color:#fff; border-radius:6px 6px 0 0; padding:12px 16px; }}
@media (prefers-color-scheme: dark) {{ header {{ background:#24476B; }} }}
header h1 {{ margin:0; font-size:20px; }}
header p {{ margin:4px 0 0; font-size:12px; opacity:.85; }}
header .en-title {{ font-size:13px; opacity:.9; margin-top:2px; }}
footer .en {{ color:var(--sub); }}
.panel {{ background:var(--paper); border-radius:0 0 6px 6px; padding:8px 16px 16px; }}
.filters {{ position:sticky; top:0; background:var(--paper); padding:8px 0; border-bottom:2px solid var(--ink); z-index:2; }}
.filters div {{ margin:4px 0; }}
.filters button {{ font:inherit; font-size:13px; margin:2px 2px; padding:4px 9px; border:1px solid var(--rule);
                  border-radius:4px; background:var(--tint); color:var(--ink); cursor:pointer; }}
.filters button.on {{ background:var(--navy); border-color:var(--navy); color:var(--paper); }}
.count {{ font-size:12px; color:var(--sub); }}
.op {{ padding:12px 0; border-bottom:1px solid var(--rule); }}
.op[hidden] {{ display:none; }}
.meta {{ font-size:13px; color:var(--sub); }}
.op h2 {{ margin:2px 0; font-size:19px; }}
.op h2 a {{ color:var(--navy); font-weight:700; text-decoration:none; margin-left:6px; }}
.badge {{ display:inline-block; font-size:12px; font-weight:700; padding:1px 7px; border-radius:3px; }}
.badge.now {{ background:var(--good); color:#fff; }}
.left {{ font-size:12px; color:var(--sub); margin-left:6px; }}
.chips {{ margin:4px 0; }}
.chip {{ display:inline-block; font-size:11px; padding:1px 6px; margin:2px 3px 0 0; border-radius:3px; background:var(--chip); }}
.chip.mode {{ border:1px solid var(--rule); background:transparent; }}
.info {{ margin:4px 0; font-size:13px; line-height:1.55; color:var(--sub); }}
.qsl {{ font-size:12px; color:var(--sub); }}
footer {{ font-size:12px; line-height:1.7; color:var(--sub); padding-top:14px; }}
footer a {{ color:var(--navy); }}
</style></head>
<body><main>
<header><h1>DXペディション予定（3か月以内）</h1>
<div class="en-title">DXpeditions — current and upcoming, next 3 months</div>
<p>運用中 Active {n_now}・全 Total {len(ops)}　更新 Updated: {updated}</p></header>
<div class="panel">
<div class="filters">
<div><button data-now="1">運用中だけ / Active only</button>{bands_btn}</div>
<div>{modes_btn}<button data-clear="1">すべて表示 / Show all</button></div>
<div class="count" id="count"></div>
</div>
{"".join(rows) or '<p>現在、予定はありません。 / No operations are listed at present.</p>'}
<footer>
バンドとモードの表示と絞り込みは、各運用の説明文（Info）から自動で推定したものです。説明に書かれていないバンドやモードで運用されることもあります。<br>
<span class="en">Band and mode tags and filters are derived automatically from each Info text; operations may also use bands or modes not mentioned there.</span><br>
出典 Source: <a href="{ADXO_TABLE}" target="_blank" rel="noopener">NG3K Announced DX Operations</a>（Bill Feidt, NG3K）。発表時点の予定で、変更・中止があります。最新の情報は出典のページでご確認ください。<br>
<span class="en">Schedules are as announced and may change or be cancelled. Please check the source page for the latest information.</span><br>
作成 By: <a href="{HOME}" target="_blank" rel="noopener">JA1BBE</a>（1日2回、自動で更新 / updated automatically twice a day）
</footer>
</div></main>
<script>
(function () {{
  var st = {{ now: false, band: null, mode: null }};
  var ops = Array.prototype.slice.call(document.querySelectorAll('.op'));
  var btns = Array.prototype.slice.call(document.querySelectorAll('.filters button'));
  function apply() {{
    var n = 0;
    ops.forEach(function (o) {{
      var ok = (!st.now || o.dataset.now === '1')
        && (!st.band || (' ' + o.dataset.bands + ' ').indexOf(' ' + st.band + ' ') >= 0)
        && (!st.mode || (' ' + o.dataset.modes + ' ').indexOf(' ' + st.mode + ' ') >= 0);
      o.hidden = !ok; if (ok) n++;
    }});
    btns.forEach(function (b) {{
      b.classList.toggle('on', !!((b.dataset.now && st.now) || (b.dataset.band && b.dataset.band === st.band)
                                || (b.dataset.mode && b.dataset.mode === st.mode)));
    }});
    document.getElementById('count').textContent = n + '件を表示中 / Showing ' + n;
  }}
  btns.forEach(function (b) {{
    b.addEventListener('click', function () {{
      if (b.dataset.clear) {{ st = {{ now: false, band: null, mode: null }}; }}
      else if (b.dataset.now) {{ st.now = !st.now; }}
      else if (b.dataset.band) {{ st.band = st.band === b.dataset.band ? null : b.dataset.band; }}
      else if (b.dataset.mode) {{ st.mode = st.mode === b.dataset.mode ? null : b.dataset.mode; }}
      apply();
    }});
  }});
  apply();
}})();
</script>
</body></html>"""


def main():
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read() if len(sys.argv) > 1 else fetch()
    now = datetime.now(timezone.utc)
    today = now.date()
    ops = [o for o in parse(text) if o["end"] >= today and o["start"] <= today + timedelta(days=DAYS)]
    ops.sort(key=lambda o: (not (o["start"] <= today <= o["end"]), o["start"], o["end"]))
    if not ops and len(sys.argv) == 1:
        sys.exit("予定を1件も読み取れませんでした（ページの形式が変わった可能性があります）。前回のページを残します。")
    jst = now + timedelta(hours=9)
    updated = f"{jst:%Y-%m-%d %H:%M} JST（{now:%H:%M} UTC）"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(ops, today, updated))
    print(f"{len(ops)}件を書き出しました: {OUT}")


if __name__ == "__main__":
    main()
