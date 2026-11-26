# -*- coding: utf-8 -*-
"""
DXペディション予定（3か月以内）のWebページを作る（GitHub Actionsで1日2回実行）
出典: NG3K Announced DX Operations テキスト版 https://www.ng3k.com/Misc/adxoplain.html
地図とバンド・時間帯の目安: 宇宙天気ナウキャスト（ja1bbe-iono）の地図データ（land.json）とエンティティの表（cty.json）、
  伝搬研究（ja1bbe/propagation）の受信の集計（paths.json）を、ページを開いたブラウザが読み込んで描く。
  各運用の位置は、ページを作るときに cty.json から求めて埋め込む（取得できないときは地図に載せない）。
使い方: python build_adxo_page.py               … ADXOを取得して docs/index.html（日英）と docs/en.html（英語）を作る
        python build_adxo_page.py 保存したファイル.html … 保存したテキスト版から作る（試験用）
標準ライブラリだけで動きます。
"""
import html, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

ADXO_URL = "https://www.ng3k.com/Misc/adxoplain.html"
ADXO_TABLE = "https://www.ng3k.com/Misc/adxo.html"
HOME = "https://ja1bbe.wixsite.com/mysite"
CTY_URL = "https://raw.githubusercontent.com/ja1bbe/ja1bbe-iono/main/docs/cty.json"   # ナウキャストと同じエンティティの表
DAYS = 92                                   # 約3か月先まで
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
OUT_EN = os.path.join(os.path.dirname(OUT), "en.html")      # 海外の局向けの英語だけの版
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
BANDS = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]
HF = ["80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]   # HFは3〜30MHz。160m（1.8MHz）は含めない
MODES = ["CW", "SSB", "FT8", "FT4", "RTTY", "SSTV", "PSK"]


def fetch():
    req = urllib.request.Request(ADXO_URL, headers={"User-Agent": "JA1BBE DXpedition page (GitHub Actions, twice a day)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_cty():
    """エンティティの表（cty.json）。取得できなければ None（地図に運用を載せないだけで、一覧は作る）"""
    try:
        req = urllib.request.Request(CTY_URL, headers={"User-Agent": "JA1BBE DXpedition page (GitHub Actions)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                      # noqa: BLE001  地図が出ないだけなので止めない
        print("cty.json を取得できませんでした（地図に運用を載せません）:", e)
        return None


# ADXO と cty.dat で書き方が大きく違うエンティティ名（正規化しても合わないもの）
ENT_ALIAS = {"peter i": "Peter 1 Island", "marianas": "Mariana Islands", "gambia": "The Gambia",
             "rodrigues i": "Rodriguez Island", "surinam": "Suriname"}


def _norm(s):
    s = html.unescape(s).lower().replace("&", " and ")
    s = re.sub(r"[.,'()\-/]", " ", s)
    m = {"i": "island", "is": "island", "isl": "island", "islands": "island", "st": "saint", "br": "british"}
    return " ".join(m.get(w, w) for w in s.split())


def locate(o, cty):
    """運用の位置（エンティティの代表位置）を (cty.jsonの番号, 緯度, 経度) で返す。
    ADXO のエンティティ名を優先し（コールサインが別エンティティのプリフィックスのこともあるため）、
    名前で見つからないときだけコールサインのプリフィックスで探す。見つからなければ None"""
    if not cty:
        return None
    ents = cty["ent"]
    if "_byname" not in cty:
        cty["_byname"] = {_norm(e[0]): i for i, e in enumerate(ents)}
    name = html.unescape(o["entity"]).strip()
    alias = ENT_ALIAS.get(name.lower())
    i = cty["_byname"].get(_norm(alias or name))
    if i is not None:
        return i, ents[i][1], ents[i][2]
    calls = [c for c in re.split(r"[\s,;]+", o["call"].upper()) if re.fullmatch(r"[A-Z0-9/]{2,15}", c)]
    for call in calls:
        v = cty["exact"].get(call)
        if v is None:
            parts = [p for p in call.split("/") if p and not re.fullmatch(r"P|M|MM|AM|QRP|A|B|LH|\d", p)]
            key = min(parts, key=len) if len(parts) > 1 else (parts[0] if parts else call)
            for n in range(len(key), 0, -1):
                if key[:n] in cty["prefix"]:
                    v = cty["prefix"][key[:n]]
                    break
        if v is not None:
            if isinstance(v, list):
                return v[0], v[1], v[2]
            return v, ents[v][1], ents[v][2]
    return None


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


FULLCALL = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]*[A-Z]$")   # 例 V26JJ、5Z4GO。J3・3B9・KH0 のようなプリフィックスだけのものは除く


def links_of(o):
    """(運用の詳細のURL, QRZ.comのURL) を返す。
    NG3KのADXOがコールサインにリンクを付けていればそれを使う（QRZ.comへのリンクならQRZ.comのボタンに回す）。
    ADXOにQRZ.comのリンクがなければ、コールサインが完全な形のときだけQRZ.comのページを作る。"""
    url = o["url"]
    web = qrz = None
    if url:
        if "qrz.com" in url.lower():
            qrz = url
        else:
            web = url
    if not qrz:
        parts = [p for p in o["call"].upper().split("/") if FULLCALL.match(p)]
        if parts:
            qrz = "https://www.qrz.com/db/" + max(parts, key=len)
    return web, qrz


def linkify(text):
    """説明文（Info）をHTML用に変換し、中のURLを押せるリンクにする。文末の「.」「,」「;」「)」はURLに含めない"""
    out, pos = [], 0
    for m in re.finditer(r"https?://[^\s<>\"]+", text):
        url = m.group(0).rstrip(".,;:)")
        out.append(html.escape(text[pos:m.start()]))
        out.append(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(url)}</a>')
        pos = m.start() + len(url)
    out.append(html.escape(text[pos:]))
    return "".join(out)


def qsl_text(q, lang="ja"):
    """ADXOのQSL欄。NG3Kの書き方: 「?」= QSLに応じない可能性、「TBA」= 後日発表"""
    q = (q or "").strip()
    if q == "?":
        return "? (may not QSL)" if lang == "en" else "?（応じない可能性 / may not QSL）"
    if q.upper() == "TBA":
        return "TBA (to be announced)" if lang == "en" else "TBA（後日発表 / to be announced）"
    return html.escape(q or "—")


def render(ops, today, updated, lang="ja"):
    E = lang == "en"
    rows = []
    for i, o in enumerate(ops):
        now = o["start"] <= today <= o["end"]
        left = (o["end"] - today).days
        mon = lambda x: f'{x:%b} {x.day}' + (f', {x.year}' if o["start"].year != o["end"].year else "")
        d = f'{mon(o["start"])} – {mon(o["end"])}'          # 月を英語の略称にして、日付の順番の誤解を防ぐ
        until = (o["start"] - today).days
        en = lambda n, w: f'{n} {w}' + ("" if n == 1 else "s")
        if E:
            state = (f'<span class="badge now">Active</span><span class="left">{en(left, "day")} left</span>'
                     if now else f'<span class="left">starts in {en(until, "day")}</span>')
        else:
            state = (f'<span class="badge now">運用中 Active</span><span class="left">残り{left}日 / {en(left, "day")} left</span>'
                     if now else f'<span class="left">{until}日後から / starts in {en(until, "day")}</span>')
        call = html.escape(o["call"])
        web, qrz = links_of(o)
        call_html = (f'<a class="call" href="{html.escape(qrz)}" target="_blank" rel="noopener">{call}</a>'
                     if qrz else f'<span class="call">{call}</span>')
        btns = ""
        if web:
            btns += f'<a class="btn" href="{html.escape(web)}" target="_blank" rel="noopener">{"Operation website" if E else "運用の詳細 / Web"}</a>'
        if qrz:
            btns += f'<a class="btn" href="{html.escape(qrz)}" target="_blank" rel="noopener">QRZ.com</a>'
        chips = "".join(f'<span class="chip">{b}</span>' for b in o["bands"])
        chips += "".join(f'<span class="chip mode">{m}</span>' for m in o["modes"])
        if o.get("lat") is not None:
            btns += f'<button type="button" class="btn mapbtn" data-i="{i}">{"Show on map" if E else "地図で見る / Map"}</button>'
        adv_t = "Suggested bands and times" if E else "望ましいバンドと時間帯の目安"
        rows.append(
            f'<article class="op" id="op{i}" data-now="{int(now)}" data-bands="{" ".join(o["bands"])}" '
            f'data-modes="{" ".join(o["modes"])}">'
            f'<div class="meta">{d}　{state}</div>'
            f'<h2>{html.escape(o["entity"])} {call_html}</h2>'
            f'<div class="azl" data-i="{i}"></div>'
            f'<div class="chips">{chips}</div>'
            f'<p class="info">{linkify(o["info"])}</p>'
            f'<div class="qsl">QSL: {qsl_text(o["qsl"], lang)}</div>'
            f'<div class="advbox"><div class="adv-t"><span class="adv-tt">{adv_t}</span><span class="vf">{"under test" if E else "検証中"}</span></div>'
            f'<div class="adv" data-i="{i}"></div></div>'
            + (f'<div class="links">{btns}</div>' if btns else "") + '</article>')
    js_ops = [{"call": o["call"], "entity": html.unescape(o["entity"]), "ent": o.get("ent"), "lat": o.get("lat"), "lon": o.get("lon"),
               "now": int(o["start"] <= today <= o["end"]), "start": o["start"].isoformat(), "bands": o["bands"]} for o in ops]
    map_html = MAP_HTML
    map_foot = MAP_FOOT_EN if E else MAP_FOOT_JA
    script = MAP_JS.replace("__LANG__", lang).replace("__OPS__", json.dumps(js_ops, ensure_ascii=False).replace("</", "<\\/"))
    bands_btn = "".join(f'<button data-band="{b}">{b}</button>' for b in BANDS)
    modes_btn = "".join(f'<button data-mode="{m}">{m}</button>' for m in ["CW", "SSB", "FT8", "FT4", "RTTY"])
    n_now = sum(1 for o in ops if o["start"] <= today <= o["end"])
    if E:
        T = dict(
            lang="en", hits="ja1bbe.github.io/dxpeditions/en.html", title="Upcoming DXpeditions — next 3 months | JA1BBE",
            header=f'''<h1>Upcoming DXpeditions — next 3 months</h1>
<div class="en-title">Current and announced DX operations, based on NG3K Announced DX Operations · <a href="index.html" style="color:#fff;">日本語</a></div>
<p>Active now {n_now} · Total {len(ops)} · Updated {updated}</p>''',
            active="Active only", clear="Show all", none="No operations are listed at present.",
            count="'Showing ' + n",
            footer=f'''Band and mode tags and filters are derived automatically from each Info text; operations may also use bands or modes not mentioned there.<br>
Source: <a href="{ADXO_TABLE}" target="_blank" rel="noopener">NG3K Announced DX Operations</a> (Bill Feidt, NG3K), used with permission. Schedules are as announced and may change or be cancelled. Please check the source page for the latest information.<br>
"Operation website" links to the operation's website as listed by NG3K; "QRZ.com" links to the station's QRZ.com page (some details may require login).<br>
Compiled by <a href="https://www.qrz.com/db/JA1BBE" target="_blank" rel="noopener">JA1BBE</a> (Tokyo, Japan) · updated automatically twice a day.<br>''')
    else:
        T = dict(
            lang="ja", hits="ja1bbe.github.io/dxpeditions", title="DXペディション予定 / DXpeditions — next 3 months | JA1BBE",
            header=f'''<h1>DXペディション予定（3か月以内）</h1>
<div class="en-title">DXpeditions — current and upcoming, next 3 months · <a href="en.html" style="color:#fff;">English</a></div>
<p>運用中 Active {n_now}・全 Total {len(ops)}　更新 Updated: {updated}</p>''',
            active="運用中だけ / Active only", clear="すべて表示 / Show all",
            none="現在、予定はありません。 / No operations are listed at present.",
            count="n + '件を表示中 / Showing ' + n",
            footer=f'''バンドとモードの表示と絞り込みは、各運用の説明文（Info）から自動で推定したものです。説明に書かれていないバンドやモードで運用されることもあります。<br>
<span class="en">Band and mode tags and filters are derived automatically from each Info text; operations may also use bands or modes not mentioned there.</span><br>
出典 Source: <a href="{ADXO_TABLE}" target="_blank" rel="noopener">NG3K Announced DX Operations</a>（Bill Feidt, NG3K）。発表時点の予定で、変更・中止があります。最新の情報は出典のページでご確認ください。<br>
<span class="en">Schedules are as announced and may change or be cancelled. Please check the source page for the latest information.</span><br>
「運用の詳細 / Web」はNG3Kのページに載っている運用者のWebサイト、「QRZ.com」は運用局のQRZ.comのページです（QRZ.comはログインしないと一部が見られない場合があります）。<br>
<span class="en">"Web" links to the operation's website as listed by NG3K; "QRZ.com" links to the station's QRZ.com page (some details may require login).</span><br>
作成 By: <a href="{HOME}" target="_blank" rel="noopener">JA1BBE</a>（1日2回、自動で更新 / updated automatically twice a day）<br>''')
    return f"""<!DOCTYPE html>
<html lang="{T['lang']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{T['title']}</title>
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
.op h2 .call {{ color:var(--navy); font-weight:700; margin-left:6px; }}
.op h2 a.call {{ text-decoration:none; }}
.op h2 a.call:hover {{ text-decoration:underline; }}
.links {{ margin-top:6px; }}
.btn {{ display:inline-block; font-size:12px; padding:3px 10px; margin:2px 6px 0 0; border:1px solid var(--navy);
       border-radius:4px; color:var(--navy); text-decoration:none; }}
.btn:hover {{ background:var(--navy); color:var(--paper); }}
.badge {{ display:inline-block; font-size:12px; font-weight:700; padding:1px 7px; border-radius:3px; }}
.badge.now {{ background:var(--good); color:#fff; }}
.left {{ font-size:12px; color:var(--sub); margin-left:6px; }}
.chips {{ margin:4px 0; }}
.chip {{ display:inline-block; font-size:11px; padding:1px 6px; margin:2px 3px 0 0; border-radius:3px; background:var(--chip); }}
.chip.mode {{ border:1px solid var(--rule); background:transparent; }}
.info {{ margin:4px 0; font-size:13px; line-height:1.55; color:var(--sub); }}
.info a {{ color:var(--navy); overflow-wrap:anywhere; }}
.qsl {{ font-size:12px; color:var(--sub); }}
footer {{ font-size:12px; line-height:1.7; color:var(--sub); padding-top:14px; }}

.op {{ scroll-margin-top:calc(var(--fh, 120px) + 8px); }}
#mapCard {{ padding:8px 0 12px; border-bottom:1px solid var(--rule); scroll-margin-top:8px; }}
#mapCard h2 {{ margin:4px 0 2px; font-size:16px; }}
.mapform {{ display:flex; flex-wrap:wrap; gap:6px 8px; align-items:center; font-size:13px; color:var(--sub); margin:6px 0; }}
.mapform select {{ font:inherit; font-size:14px; max-width:100%; color:var(--ink); background:var(--tint); border:1px solid var(--rule); border-radius:4px; padding:4px 6px; }}
.mapform input {{ width:10em; font:600 16px ui-monospace,Menlo,Consolas,monospace; text-transform:uppercase; color:var(--ink);
                  background:var(--tint); border:1px solid var(--rule); border-radius:4px; padding:4px 7px; }}
.mapform button, .upbtn {{ font:inherit; font-size:13px; padding:4px 10px; border:1px solid var(--navy); border-radius:4px;
                  background:transparent; color:var(--navy); cursor:pointer; }}
#dxMap {{ width:100%; max-width:560px; aspect-ratio:1/1; display:block; margin:8px auto 0; cursor:pointer; }}
.legend {{ display:flex; flex-wrap:wrap; justify-content:center; gap:3px 12px; font-size:11px; color:var(--sub); margin-top:6px; }}
.legend i {{ display:inline-block; width:12px; height:9px; border-radius:2px; margin-right:4px; vertical-align:-1px; }}
.legend i.dot {{ width:10px; height:10px; border-radius:50%; }}
.fine {{ font-size:12px; color:var(--sub); line-height:1.6; }}
#mapInfo {{ font-size:13px; line-height:1.6; min-height:1.6em; margin-top:6px; }}
.layerbtns {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:center; margin-top:8px; }}
.upbtn.on {{ background:var(--navy); color:var(--paper); }}
#layerNote div {{ margin-top:4px; }}
.azl {{ font-size:13px; color:var(--navy); margin:2px 0; }}
#mapInfo a {{ color:var(--navy); }}
button.btn {{ font:inherit; font-size:12px; background:transparent; cursor:pointer; }}
.advbox {{ margin:6px 0 2px; padding:6px 10px; border-left:3px solid #c9971f; background:rgba(216,177,74,.10); border-radius:0 4px 4px 0; }}
.adv-t {{ font-size:12px; font-weight:700; color:#8a6410; }}
@media (prefers-color-scheme: dark) {{ .adv-t {{ color:#d8b14a; }} }}
.adv-t .vf {{ color:#d64545; font-weight:400; margin-left:6px; white-space:nowrap; }}
.adv {{ font-size:12.5px; line-height:1.65; }}
.adv-p {{ margin:2px 0; }}
.adv-h {{ font-weight:700; font-size:12px; color:var(--sub); margin-top:4px; }}
.adv-b {{ color:var(--sub); font-size:11px; }}
.adv-best {{ margin:3px 0; }}
.adv-w {{ margin:3px 0; color:#b3361f; }}
@media (prefers-color-scheme: dark) {{ .adv-w {{ color:#f08a6b; }} }}
.adv-n {{ color:var(--sub); font-size:12px; margin:2px 0; }}
.adv-r {{ margin-top:2px; }}
footer a {{ color:var(--navy); }}
</style></head>
<body><main>
<header>{T['header']}</header>
<div class="panel">
{map_html}
<div class="filters">
<div><button data-now="1">{T['active']}</button>{bands_btn}</div>
<div>{modes_btn}<button data-clear="1">{T['clear']}</button></div>
<div class="count" id="count"></div>
</div>
{"".join(rows) or f"<p>{T['none']}</p>"}
<footer>
{T['footer']}{map_foot}<a href="https://hits.sh/{T['hits']}/" target="_blank" rel="noopener"><img alt="Hits" src="https://hits.sh/{T['hits']}/.svg" style="vertical-align:middle;margin-top:6px;"></a>
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
    document.getElementById('count').textContent = {T['count']};
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
<script>
{script}
</script>
</body></html>"""

# ---- 先頭の地図（宇宙天気ナウキャストの「JA1BBE 伝搬レーダー」と同じ正距方位図）
MAP_HTML = """<section id="mapCard">
<h2 id="mapTitle"></h2>
<div class="fine" id="mapLead"></div>
<div class="mapform"><label for="myGrid" id="myLab"></label><input id="myGrid" value="PM95" maxlength="15" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="JA1BBE / PM95RN"><button id="gridGo" type="button"></button></div>
<div class="mapform"><label for="opSel" id="opLab"></label><select id="opSel"></select></div>
<div class="fine" id="stInfo"></div>
<canvas id="dxMap" role="img" aria-label="Azimuthal equidistant map / 正距方位図"></canvas>
<div class="fine" id="mapTime" style="text-align:center"></div>
<div class="legend" id="legend"></div>
<div id="mapInfo"></div>
<div class="layerbtns"><button id="magBtn" type="button" class="upbtn"></button><button id="drapBtn" type="button" class="upbtn"></button><button id="stormBtn" type="button" class="upbtn"></button><button id="upBtn" type="button" class="upbtn"></button></div>
<div class="fine" id="layerNote"></div>
<noscript><p class="fine">The map needs JavaScript. / 地図の表示には JavaScript が必要です。</p></noscript>
</section>"""
MAP_FOOT_JA = """地図と「望ましいバンドと時間帯の目安」（検証中）：位置はエンティティの代表位置（cty.dat）で、実際の運用地とは数百km違うことがあります。「物理の目安」は宇宙天気ナウキャストと同じ判定で、ローバンドは経路の大半が夜（太陽高度−6°以下）になる時刻（短経路がオーロラ帯を通るか昼側が多いときは長経路）、ミドルは経路に昼と夜が混ざる時刻、ハイバンドは経路の大半が昼で SFI が十分な時刻です。運用中のものはこれから24時間（いまのオーロラ帯を含む）、予定のものは運用開始日の太陽の位置で計算します。電離層の詳しい計算（MUF の予測）ではありません。6m は目安に含めていません。自局が日本国内のときは、PSK Reporter で日本の局がそのエンティティ（記録がなければ周辺の大区画）の信号を受信できていた時間帯（抜き取りの3割以上）も示し、物理の目安とそろう時間帯を「おすすめ」としています。過去のペディションなど、たまたま運用があった時期の記録です。<br>
<span class="en">Map and band/time guide (under test): positions are entity centres (cty.dat). The physics guide follows JA1BBE Space Weather Nowcast: low bands when most of the path is dark, mid bands when the path mixes day and night, high bands when most of the path is sunlit with adequate SFI. Not a MUF prediction.</span><br>
地図の重ね描きはいまの時刻の値です：オーロラ帯は NOAA OVATION（30〜90分先の推定）、D層の吸収は NOAA D-RAP、嵐の広がりは太陽風（NOAA RTSW）の Bz と速さから見積もった目安（検証中）、地磁気緯度は棒磁石とみなした近似です。ずらした方位は、オーロラ帯を避けて途中で曲がる経路の目安で、届くことを保証するものではありません。自局をコールサインで入れたときは、エンティティの代表位置で計算します。表示の言語は、自局が日本国内なら日本語、国外なら英語です。<br>
地図：Natural Earth（land.json）、宇宙天気：NOAA SWPC、受信の記録：PSK Reporter のデータを JA1BBE が集計（<a href="https://ja1bbe.github.io/ja1bbe-iono/m.html" target="_blank" rel="noopener">宇宙天気ナウキャスト</a>と同じもの）。<br>"""
MAP_FOOT_EN = """Map and “suggested bands and times” (under test): positions are entity centres from cty.dat and may differ from the actual site by a few hundred km. The physics guide uses the same rules as JA1BBE Space Weather Nowcast: low bands when most of the path is dark (sun below −6°), using the long path when the short path crosses the auroral oval or is mostly sunlit; mid bands when the path mixes day and night; high bands when most of the path is sunlit and SFI is adequate. Active operations: next 24 hours, including the current auroral oval. Upcoming operations: sun positions on the start date. This is not a MUF prediction, and 6 m is not covered. When your station is in Japan, hours when Japanese stations heard the entity on PSK Reporter (in at least 30% of samples; nearby grid square if the entity has no record) are also shown, and hours where the record and physics agree are marked “Best bet”.<br>
Map overlays are for the current time: auroral oval from NOAA OVATION (30–90 min forecast), D-region absorption from NOAA D-RAP, storm extent estimated from solar-wind Bz and speed (NOAA RTSW; under test), and geomagnetic latitude from a dipole approximation. A skewed heading is a hint for a path bending around the auroral oval, not a guarantee. A callsign is placed at its entity centre. Text appears in Japanese when your station is in Japan, otherwise in English.<br>
Map: Natural Earth (land.json). Space weather: NOAA SWPC. Reception record: PSK Reporter data compiled by JA1BBE (same as <a href="https://ja1bbe.github.io/ja1bbe-iono/nowcast_en.html" target="_blank" rel="noopener">Space Weather Nowcast</a>).<br>"""

MAP_JS = r'''(() => {
  // ---- 地図と「バンドと時間帯の目安」（宇宙天気ナウキャストの JA1BBE 伝搬レーダーと同じ計算。検証中）
  // 表示の言語は、自局が日本国内なら日本語、国外なら英語（自局を入れていないときは、そのページの言語）
  const PAGE_LANG = '__LANG__', OPS = __OPS__;
  const IONO = 'https://ja1bbe.github.io/ja1bbe-iono/';
  const SUMMARY_URL = 'https://raw.githubusercontent.com/ja1bbe/propagation/main/data/summary/paths.json';
  const NOAA = 'https://services.swpc.noaa.gov';
  const RAD = Math.PI / 180, EARTH = 6371, HALF = Math.PI * EARTH, GMPOLE = { lat: 80.8, lon: -72.6 };
  const KNOWN = { 'JA1BBE': 'PM95RN' };      // 位置がわかっている局（コールサインで入れてもこのグリッドで計算）
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const LS = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  const rows = d => Array.isArray(d) && Array.isArray(d[0]) ? d.slice(1).map(r => Object.fromEntries(d[0].map((h, i) => [h, r[i]]))) : (d || []);
  let STATION = null, LAND = null, AUR = null, DRAP = null, SW = null, SFI = null, SUMMARY = null, CTY = null, SEL = null, HITS = [], LG = PAGE_LANG, T = null;
  const flag = (k, def) => { const v = LS(k); return v === null ? def : v === '1'; };
  let SHOW_UP = flag('dx.showUp', false), MAG_ON = flag('dx.mag', true), DRAP_ON = flag('dx.drap', true), STORM_ON = flag('dx.storm', true);

  // ---- 太陽と経路の計算（ナウキャストと同じ式）
  function sunElev(lat, lon, t) {
    const d = new Date(t), doy = (Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5;
    const hr = d.getUTCHours() + d.getUTCMinutes() / 60, g = 2 * Math.PI / 365 * (doy - 1 + (hr - 12) / 24);
    const eq = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
    const dec = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
    const ha = ((hr * 60 + eq + 4 * lon) / 4 - 180) * RAD, la = lat * RAD;
    return Math.asin(Math.sin(la) * Math.sin(dec) + Math.cos(la) * Math.cos(dec) * Math.cos(ha)) / RAD;
  }
  const magLat = (lat, lon) => Math.asin(Math.sin(lat * RAD) * Math.sin(GMPOLE.lat * RAD) + Math.cos(lat * RAD) * Math.cos(GMPOLE.lat * RAD) * Math.cos((lon - GMPOLE.lon) * RAD)) / RAD;
  function bearingDist(la1, lo1, la2, lo2) {
    const p1 = la1 * RAD, p2 = la2 * RAD, dl = (lo2 - lo1) * RAD;
    const d = Math.acos(Math.max(-1, Math.min(1, Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(dl))));
    const az = (Math.atan2(Math.sin(dl) * Math.cos(p2), Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)) / RAD + 360) % 360;
    return { az, km: d * EARTH };
  }
  function dest(la, lo, az, km) {
    const d = km / EARTH, p1 = la * RAD, t = az * RAD;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(t));
    const l2 = lo * RAD + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
    return [p2 / RAD, ((l2 / RAD + 540) % 360) - 180];
  }
  function aurAt(lat, lon) {
    if (!AUR) return null;
    let Lo = Math.round(lon); Lo = ((Lo % 360) + 360) % 360;
    return AUR[Lo * 181 + Math.max(-90, Math.min(90, Math.round(lat))) + 90];
  }
  function parseAur(d) {
    const g = new Float32Array(360 * 181);
    for (const [lo, la, a] of d.coordinates) { const Lo = ((Math.round(lo) % 360) + 360) % 360, A = Math.round(la); if (A >= -90 && A <= 90) g[Lo * 181 + A + 90] = a; }
    return g;
  }
  // D層の吸収（NOAA D-RAP。電波が1dB以上吸収される周波数の上限 MHz）
  function parseDrap(txt) {
    const rs = [], lat = []; let valid = '', xr = '';
    for (const ln of txt.split(/\r?\n/)) { let m;
      if ((m = ln.match(/Product Valid At\s*:\s*(.+)/))) valid = m[1].trim();
      else if ((m = ln.match(/X-RAY Message\s*:\s*(.*)/))) xr = m[1].trim();
      else if ((m = ln.match(/^\s*(-?\d+)\s*\|(.*)$/))) { lat.push(+m[1]); rs.push(m[2].trim().split(/\s+/).map(Number)); } }
    return rs.length ? { lat, rows: rs, valid, xr } : null;
  }
  function drapAt(la, lo) {
    if (!DRAP) return null; const n = DRAP.lat.length, i = Math.max(0, Math.min(n - 1, Math.round((DRAP.lat[0] - la) / (DRAP.lat[0] - DRAP.lat[1] || 2)))), row = DRAP.rows[i];
    const nc = row.length, j = ((Math.round((lo + 178) / (360 / nc)) % nc) + nc) % nc; return row[j];
  }
  const drapMax = () => { if (!DRAP) return null; let m = 0; for (const r of DRAP.rows) for (const v of r) if (v > m) m = v; return m; };
  // 嵐の広がり：Bz の南向きと太陽風の速さから、オーロラ帯の赤道側の縁（地磁気緯度）を見積もる（ナウキャストと同じ。検証中）
  const bzActive = () => SW && SW.bz30 != null && (SW.bz30 <= -10 || (SW.bz30 <= -5 && (SW.south || 0) >= 60));
  function stormEdge() {
    if (!SW) return null; const bs = Math.max(0, -(SW.bz30 ?? 0)), v = SW.sp ?? 400, E = v * bs * 1e-3;
    const kp = Math.max(Math.min(9, 1 + 0.6 * E), SW.kp ?? 0); return { edge: Math.max(45, Math.min(64, 66 - 2 * kp)), kp, show: bzActive() || kp >= 4 };
  }
  function southMin(sr) {      // 10分平均の Bz が −3nT 以下で続いている時間（分）
    if (!sr || sr.length < 2) return 0; const end = sr[sr.length - 1][0]; let t0 = end;
    for (let i = sr.length - 1; i >= 0; i--) { const t = sr[i][0], w = sr.filter(r => r[0] <= t && r[0] > t - 600e3).map(r => r[1]); if (!w.length || w.reduce((a, b) => a + b, 0) / w.length > -3) break; t0 = t; }
    return Math.round((end - t0) / 60e3);
  }
  function gridToLL(g) {
    g = String(g || '').trim().toUpperCase();
    if (!/^[A-R]{2}[0-9]{2}([A-X]{2})?$/.test(g)) return null;
    let lon = (g.charCodeAt(0) - 65) * 20 - 180 + (+g[2]) * 2, lat = (g.charCodeAt(1) - 65) * 10 - 90 + (+g[3]);
    if (g.length === 6) { lon += (g.charCodeAt(4) - 65) * (2 / 24) + 1 / 24; lat += (g.charCodeAt(5) - 65) * (1 / 24) + 1 / 48; } else { lon += 1; lat += 0.5; }
    return { grid: g, lat, lon };
  }
  const llToGrid = (lat, lon) => { lon += 180; lat += 90; return String.fromCharCode(65 + Math.floor(lon / 20)) + String.fromCharCode(65 + Math.floor(lat / 10)) + Math.floor((lon % 20) / 2) + Math.floor(lat % 10); };
  // 日本国内かどうか（南西諸島・小笠原を含み、朝鮮半島・台湾・ロシア沿岸・サハリンを除く大まかな範囲。南鳥島は別に足す）
  const JA_POLY = [[24.0, 122.3], [28.0, 125.6], [32.0, 127.8], [33.6, 128.6], [34.6, 129.1], [35.3, 130.0], [37.5, 131.3], [42.0, 137.0], [45.0, 139.5], [45.6, 141.4], [45.6, 142.3], [44.6, 145.4], [43.2, 146.0], [40.0, 146.0], [24.0, 146.0]];
  function isJapan(lat, lon) {
    if (lat >= 23.5 && lat <= 25 && lon >= 153 && lon <= 155) return true;
    let inside = false;
    for (let i = 0, j = JA_POLY.length - 1; i < JA_POLY.length; j = i++) {
      const [yi, xi] = JA_POLY[i], [yj, xj] = JA_POLY[j];
      if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  // コールサイン → エンティティ（cty.dat。ナウキャストと同じ探し方）
  function ent(v) { const i = Array.isArray(v) ? v[0] : v, e = CTY.ent[i]; return { name: e[0], lat: Array.isArray(v) ? v[1] : e[1], lon: Array.isArray(v) ? v[2] : e[2] }; }
  function lookupCall(call) {
    if (CTY.exact[call] != null) return ent(CTY.exact[call]);
    if (/\/MM$/.test(call)) return null;
    const parts = call.split('/'), IGN = /^(P|M|MM|AM|QRP|A|B|LH|\d)$/, longest = parts.reduce((a, b) => b.length > a.length ? b : a, '');
    let key = parts[0]; const others = parts.filter(p => p && !IGN.test(p) && p !== longest);
    if (parts.length > 1 && others.length) key = others[0].length <= parts[0].length ? others[0] : parts[0];
    for (let n = key.length; n > 0; n--) { const p = key.slice(0, n); if (CTY.prefix[p] != null) return ent(CTY.prefix[p]); }
    return null;
  }
  function pathStats(az, km, t, useAur) {
    let dark = 0, n = 0, mm = 0, au = null;
    for (let x = 0; x <= km; x += 250) {
      const [la, lo] = dest(STATION.lat, STATION.lon, az, x); n++;
      if (sunElev(la, lo, t) < -6) dark++;
      const m = magLat(la, lo); if (Math.abs(m) > Math.abs(mm)) mm = m;
      if (useAur) { const a = aurAt(la, lo); if (a != null) au = Math.max(au ?? 0, a); }
    }
    return { az, km, dark: dark / n, mag: mm, aur: au };
  }
  // オーロラ帯を避ける「ずらした方位」（ナウキャストと同じ探し方：左右60°まで5°刻み、遠回りは大圏の1.3倍まで）
  function seg(la1, lo1, la2, lo2, step) { const g = bearingDist(la1, lo1, la2, lo2), out = []; for (let x = 0; x < g.km; x += step) out.push(dest(la1, lo1, g.az, x)); out.push([la2, lo2]); return { pts: out, km: g.km }; }
  function skewSearch(g, tgt) {
    const cand = [];
    for (let d = 5; d <= 60; d += 5) for (const s of [1, -1]) {
      const az = (g.az + s * d + 360) % 360; let best = null;
      for (let D = 1500; D <= g.km + 1000; D += 500) {
        const [pla, plo] = dest(STATION.lat, STATION.lon, az, D), a = seg(STATION.lat, STATION.lon, pla, plo, 250), b = seg(pla, plo, tgt.lat, tgt.lon, 250), tot = a.km + b.km;
        if (tot > g.km * 1.3) continue;
        const pts = a.pts.concat(b.pts); let mm = 0, au = null;
        for (const [la, lo] of pts) { const m = Math.abs(magLat(la, lo)); if (m > mm) mm = m; const x = aurAt(la, lo); if (x != null) au = Math.max(au ?? 0, x); }
        if (AUR ? (au ?? 0) >= 10 : mm >= 60) continue;
        if (!best || tot < best.km) best = { az, off: s * d, km: tot, turn: [pla, plo], pts };
      }
      if (best) cand.push(best);
    }
    if (!cand.length) return null;
    cand.sort((x, y) => Math.abs(x.off) - Math.abs(y.off) || x.km - y.km); const c = cand[0]; c.extra = c.km - g.km; return c;
  }
  // 選んだ運用の経路（いまの時刻）
  function route(o) {
    const g = bearingDist(STATION.lat, STATION.lon, o.lat, o.lon), now = Date.now();
    const sp = pathStats(g.az, g.km, now, !!AUR), lp = pathStats((g.az + 180) % 360, 2 * HALF - g.km, now, !!AUR);
    const needSkew = AUR ? (sp.aur ?? 0) >= 10 : Math.abs(sp.mag) >= 62, sk = needSkew ? skewSearch(g, o) : null;
    return { g, sp, lp, needSkew, sk };
  }

  // ---- 文言（日本語・英語）
  const TJ = {
    title: 'いま運用中のペディション（地図）', lead: '自局を中心にした正距方位図です。中心から見た方向が大圏方位（上が真北）、中心からの距離が実際の距離です。赤い印が運用中（エンティティの代表位置）。地図はいまの時刻の昼夜・オーロラ帯・D層の吸収・嵐の広がりを重ねています。',
    myLab: '自局（コールサインかグリッド）', go: '変更', opLab: 'ペディション', opNone: '― 選ぶ ―', opNow: '運用中', opUp: d => `${d}日後から`,
    sp: '短経路', lp: '長経路', skew: 'ずらした方位', low: 'ローバンド', mid: 'ミドル', high: 'ハイバンド',
    leg: ['運用中', '予定', '短経路', '長経路', 'ずらした方位', '夜', '薄明', 'オーロラ10〜30%', '30%以上', 'D層の吸収', '嵐の広がり'],
    magBtn: '地磁気緯度線', drapBtn: 'D層の吸収', stormBtn: '嵐の広がり', upBtn: '14日以内の予定',
    magNote: '点線は地磁気緯度 0°・±30°・±70°、橙は ±60°（静穏時のオーロラ帯の赤道側の縁の目安）。地球の磁場を棒磁石とみなした近似です。',
    drapNote: (v, mx, xr) => `D層の吸収（NOAA D-RAP、${esc(v)}）：1dB以上吸収される周波数の上限が 1MHz 以上を橙、5MHz 以上を濃い橙、10MHz 以上を赤紫で塗っています。いまの最大 ${mx.toFixed(1)}MHz。` + (mx < 1 ? 'いまは X線が平常で塗る範囲はありませんが、ふだんの昼の吸収は含まれないため、160m・80m は昼側で強く吸収されます。' : '') + (xr ? `X線：${esc(xr)}。` : ''),
    drapNA: 'D層の吸収のデータを読み込めていません。',
    stormNote: se => se.show ? `嵐の広がり（検証中）：いまの Bz・太陽風（Kp ${se.kp.toFixed(1)} 相当）から、オーロラ帯の赤道側の縁が地磁気緯度 ${se.edge.toFixed(0)}° 付近まで広がる見込みです（赤い破線）。選んだ経路のうち、その内側の区間を赤く示します。` : `嵐の広がり：いまは Bz の南向きが弱く Kp も低いため、大きな広がりは見込まれず描いていません。`,
    stormNA: '太陽風のデータを読み込めていません。',
    at: t => `地図の時刻：${jstStr(t)}（日本時間）`, hint: '地図の印を押すか、上の「ペディション」で選ぶと、自局からの伝搬経路を描きます。',
    info: (o, r) => `<b>${esc(o.call)}</b> ${esc(o.entity)}　短経路 <b>${r.g.az.toFixed(0)}°</b>・長経路 ${((r.g.az + 180) % 360).toFixed(0)}°・${kmStr(r.g.km)} km` +
      `<br>${T.spState(r.sp)}` + (r.sk ? `<br><span style="color:#b25ee8">ずらした方位 <b>${r.sk.az.toFixed(0)}°</b> を試す価値あり（${llToGrid(r.sk.turn[0], r.sk.turn[1])} 付近で曲がる経路、遠回り 約${kmStr(r.sk.extra)} km。検証中）</span>` : r.needSkew ? '<br>左右60°までずらしても、オーロラ帯を避けて届く経路は見つかりませんでした。' : ''),
    spState: sp => `短経路：地磁気緯度 ${sp.mag >= 0 ? 'N' : 'S'}${Math.abs(sp.mag).toFixed(0)}° まで、途中の${Math.round(sp.dark * 100)}%が夜` + (sp.aur == null ? '' : sp.aur >= 30 ? `、<b style="color:#d64545">オーロラ帯を通過（${sp.aur.toFixed(0)}%）</b>` : sp.aur >= 10 ? `、オーロラ帯の縁（${sp.aur.toFixed(0)}%）` : ''),
    toList: '一覧の案内へ ↓', noneActive: 'いま運用中のペディションはありません。',
    bad: g => `「${esc(g)}」を判別できなかったため、PM95 を中心にしています。グリッドロケータ（4桁か6桁）か、コールサインで入れてください。`,
    centre: (n, note) => `自局：${esc(n)}（${note}）を中心にしています。`, gridNote: g => `グリッド ${g} の中心`, knownNote: g => `登録済みのグリッド ${g}`,
    callNote: (e, g) => `${esc(e)} の代表位置 ${g}。正確にはグリッドロケータで入れてください`, ctyFail: 'コールサインの表を読み込めませんでした。グリッドロケータで入れてください。',
    az: (n, sp, lp, km) => `方位（${esc(n)} から）<b>${sp}°</b>　長経路 ${lp}°　${km} km`,
    advTitle: '望ましいバンドと時間帯の目安', vf: '検証中', show: '地図で見る',
    allDay: '終日', mostDay: x => `ほぼ終日（${x}を除く）`, noLow: '経路全体が夜になる時刻はありません', aurLow: 'いまはなし（夜になる短経路がオーロラ帯を通過し、長経路は夜になりません）',
    noMid: '―', ctrl: '（SFI が低めか、昼の区間が多くないため控えめ）', noHigh: '経路の大半が昼になる時刻はありません',
    physNow: '物理の目安（これから24時間）', physOn: d => `物理の目安（運用開始日 ${d} の太陽の位置で計算）`,
    rec: (days, lab) => `日本で受信できていた時間帯（PSK Reporter、直近${days}日間${lab}）`, recNear: f => `、周辺の大区画 ${f}`,
    recNone: '日本でよく受信できていた時間帯（抜き取りの3割以上）は、まだありません。', agree: 'おすすめ',
    agreeWhy: '（受信の記録と物理の目安がそろう時間帯）', agreeNear: '（周辺の大区画の受信の記録と、物理の目安がそろう時間帯）',
    polarNow: a => `短経路はいまオーロラ帯を通過しています（${a}%）。ローバンドは弱まりやすく、長経路やずらした方位も試す価値があります。`,
    polar: m => `短経路は地磁気緯度 ${m}° まで上がり、オーロラ帯の近くを通ります。地磁気が乱れると（Kp 4以上）ローバンドから弱まります。`,
    skewAdv: (a, g) => `ずらした方位 <b>${a}°</b> を試す価値あり（${g} 付近で曲がる経路。検証中）`,
    noPos: '位置が分からないため、地図には載せていません。', same: '自局に近すぎるため、目安を出していません。', loading: '計算しています…',
    sep: '、', sepL: '／', day: ms => { const d = new Date(ms); return `${d.getUTCMonth() + 1}月${d.getUTCDate()}日`; },
    hrs: (h, e) => `${h}〜${e} UTC（日本時間 ${(h + 9) % 24}〜${(e + 9) % 24}時）`,
  };
  const TE = {
    title: 'DXpeditions active now — map', lead: 'Azimuthal equidistant map centred on your station: direction from the centre is the great-circle heading (true north up), distance from the centre is the true distance. Red markers are operations active now (entity centre). The map shows day and night, the auroral oval, D-region absorption and storm extent at the current time.',
    myLab: 'Your callsign or grid', go: 'Set', opLab: 'DXpedition', opNone: '— select —', opNow: 'active', opUp: d => `starts in ${d} day${d === 1 ? '' : 's'}`,
    sp: 'Short path', lp: 'Long path', skew: 'Skewed heading', low: 'Low bands', mid: 'Mid bands', high: 'High bands',
    leg: ['Active', 'Upcoming', 'Short path', 'Long path', 'Skewed', 'Night', 'Twilight', 'Aurora 10–30%', '≥30%', 'D-region absorption', 'Storm extent'],
    magBtn: 'Geomagnetic latitude', drapBtn: 'D-region absorption', stormBtn: 'Storm extent', upBtn: 'Upcoming (14 days)',
    magNote: 'Dotted lines: geomagnetic latitude 0°, ±30°, ±70°; orange: ±60° (equatorward edge of the quiet-time auroral oval). Dipole approximation.',
    drapNote: (v, mx, xr) => `D-region absorption (NOAA D-RAP, ${esc(v)}): highest frequency with ≥1 dB absorption — orange ≥1 MHz, dark orange ≥5 MHz, magenta ≥10 MHz. Current maximum ${mx.toFixed(1)} MHz.` + (mx < 1 ? ' X-rays are quiet, so nothing is shaded; normal daytime absorption is not included, and 160/80 m are still strongly absorbed on the sunlit side.' : '') + (xr ? ` X-ray: ${esc(xr)}.` : ''),
    drapNA: 'D-region absorption data could not be loaded.',
    stormNote: se => se.show ? `Storm extent (under test): from the current Bz and solar wind (≈Kp ${se.kp.toFixed(1)}), the equatorward edge of the auroral oval may reach geomagnetic latitude ${se.edge.toFixed(0)}° (red dashed line). Sections of the selected path inside it are drawn in red.` : 'Storm extent: Bz is not strongly southward and Kp is low, so no expansion is drawn.',
    stormNA: 'Solar wind data could not be loaded.',
    at: t => `Map time: ${new Date(t).toISOString().slice(0, 16).replace('T', ' ')} UTC`, hint: 'Tap a marker or pick a DXpedition above to draw the path from your station.',
    info: (o, r) => `<b>${esc(o.call)}</b> ${esc(o.entity)} — short path <b>${r.g.az.toFixed(0)}°</b>, long path ${((r.g.az + 180) % 360).toFixed(0)}°, ${kmStr(r.g.km)} km` +
      `<br>${T.spState(r.sp)}` + (r.sk ? `<br><span style="color:#b25ee8">Worth trying a skewed heading of <b>${r.sk.az.toFixed(0)}°</b> (path bending near ${llToGrid(r.sk.turn[0], r.sk.turn[1])}, about ${kmStr(r.sk.extra)} km longer; under test)</span>` : r.needSkew ? '<br>No path avoiding the auroral oval was found within ±60°.' : ''),
    spState: sp => `Short path: up to geomagnetic latitude ${sp.mag >= 0 ? 'N' : 'S'}${Math.abs(sp.mag).toFixed(0)}°, ${Math.round(sp.dark * 100)}% in darkness` + (sp.aur == null ? '' : sp.aur >= 30 ? `, <b style="color:#d64545">crosses the auroral oval (${sp.aur.toFixed(0)}%)</b>` : sp.aur >= 10 ? `, edge of the auroral oval (${sp.aur.toFixed(0)}%)` : ''),
    toList: 'See details ↓', noneActive: 'No operations are active right now.',
    bad: g => `“${esc(g)}” was not recognised; the map is centred on PM95. Enter a 4- or 6-character grid or a callsign.`,
    centre: (n, note) => `Your station: ${esc(n)} (${note}).`, gridNote: g => `centre of grid ${g}`, knownNote: g => `registered grid ${g}`,
    callNote: (e, g) => `centre of ${esc(e)}, ${g}; enter your grid for accuracy`, ctyFail: 'The callsign table could not be loaded. Please enter a grid locator.',
    az: (n, sp, lp, km) => `Heading from ${esc(n)} <b>${sp}°</b>　long path ${lp}°　${km} km`,
    advTitle: 'Suggested bands and times', vf: 'under test', show: 'Show on map',
    allDay: 'all day', mostDay: x => `almost all day (except ${x})`, noLow: 'no hour with the whole path in darkness', aurLow: 'none now: the dark short path crosses the auroral oval, and the long path is not dark',
    noMid: '—', ctrl: ' (modest: SFI is low or the path is only partly sunlit)', noHigh: 'no hour with most of the path in daylight',
    physNow: 'Physics guide, next 24 h', physOn: d => `Physics guide for ${d} (start of operation)`,
    rec: (days, lab) => `Heard in Japan (PSK Reporter, last ${days} days${lab})`, recNear: f => `, nearby square ${f}`,
    recNone: 'No hour yet in which Japanese stations heard this entity in 30% or more of the samples.', agree: 'Best bet',
    agreeWhy: '(record and physics agree)', agreeNear: '(record from the surrounding square and physics agree)',
    polarNow: a => `The short path crosses the auroral oval now (${a}%). Low bands may be weak; try the long path or a skewed heading.`,
    polar: m => `The short path reaches geomagnetic latitude ${m}°, close to the auroral zone. Low bands suffer when Kp ≥ 4.`,
    skewAdv: (a, g) => `Worth trying a skewed heading of <b>${a}°</b> (path bending near ${g}; under test)`,
    noPos: 'Location unknown — not shown on the map.', same: 'Too close to your station for path advice.', loading: 'Calculating…',
    sep: ', ', sepL: '; ', day: ms => new Date(ms).toISOString().slice(0, 10),
    hrs: (h, e) => `${String(h).padStart(2, '0')}–${String(e).padStart(2, '0')} UTC`,
  };
  const kmStr = km => (Math.round(km / 100) * 100).toLocaleString('en-US');
  const jstStr = t => { const d = new Date(t + 9 * 3600e3), p = n => String(n).padStart(2, '0'); return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`; };
  function windows(hs) {      // 時刻の集合 → 「21〜24 UTC（日本時間 6〜9時）」（ナウキャストの gWindows と同じ）
    if (!hs.length) return '';
    const on = Array(24).fill(false); hs.forEach(h => on[h] = true);
    if (on.every(Boolean)) return T.allDay;
    if (hs.length >= 18) return T.mostDay(windows([...Array(24).keys()].filter(h => !on[h])));
    let s = 0; while (on[s]) s = (s + 1) % 24;
    const out = []; let i = 0;
    while (i < 24) { const h = (s + i) % 24; if (!on[h]) { i++; continue; } let n = 0; while (n < 24 && on[(h + n) % 24]) n++; out.push(T.hrs(h, (h + n) % 24)); i += n; }
    return out.join(T.sep);
  }
  const GROUPS = { low: ['160m', '80m', '60m', '40m'], mid: ['30m', '20m', '17m'], high: ['15m', '12m', '10m'] };
  const gLv = c => c === 'A' ? 10 : (parseInt(c, 10) || 0);
  const isoDay = s => Date.parse(s + 'T00:00:00Z');

  // ---- 物理の目安（ナウキャストの gPhysics と同じ判定）。運用中はこれから24時間（いまのオーロラ帯も使う）、予定は運用開始日
  function physics(g, base, useAur) {
    const sfi = SFI ?? 100, res = { low: [], mid: [], high: [] }, now = Date.now();
    for (let h = 0; h < 24; h++) {
      let t = base + h * 3600e3 + 1800e3; if (useAur && t < now - 1800e3) t += 864e5;
      const sp = pathStats(g.az, g.km, t, useAur), lp = pathStats((g.az + 180) % 360, 2 * HALF - g.km, t, useAur), spBad = sp.aur != null && sp.aur >= 30;
      let lo = 0, lpUse = false;
      if (sp.dark >= 0.8 && !spBad) lo = 2; else if (lp.dark >= 0.8 && (spBad || sp.dark < 0.5)) { lo = 2; lpUse = true; } else if (sp.dark >= 0.6) lo = 1;
      res.low.push({ v: lo, lp: lpUse, blk: lo < 2 && sp.dark >= 0.8 && spBad });
      res.mid.push({ v: sp.dark > 0.2 && sp.dark < 0.8 ? 2 : 1 });
      res.high.push({ v: sp.dark <= 0.2 && sfi >= 120 ? 2 : sp.dark <= 0.4 && sfi >= 90 ? 1 : 0 });
    }
    return res;
  }
  function record(o, bands) {      // 日本で受信できていた時間帯（抜き取りの3割以上。自局が日本のときだけ）
    if (!SUMMARY || !isJapan(STATION.lat, STATION.lon)) return null;
    let data = o.ent != null ? SUMMARY.e[String(o.ent)] : null, lab = '';
    if (!data) { const f = llToGrid(o.lat, o.lon).slice(0, 2); data = SUMMARY.f[f]; lab = T.recNear(f); }
    const out = [];
    if (data) for (const b of bands) { const d = data[b]; if (!d || !d.r) continue; const hs = [...d.r].map((c, h) => gLv(c) >= 3 ? h : -1).filter(h => h >= 0); if (hs.length) out.push({ b, hs }); }
    return { lab, out };
  }
  const opBands = o => { const bs = (o.bands && o.bands.length ? o.bands : [...GROUPS.low, ...GROUPS.mid, ...GROUPS.high]).filter(b => b !== '6m'); return bs.length ? bs : GROUPS.high; };

  function advice(o) {
    if (o.lat == null) return `<p class="adv-n">${T.noPos}</p>`;
    const g = bearingDist(STATION.lat, STATION.lon, o.lat, o.lon);
    if (g.km < 300) return `<p class="adv-n">${T.same}</p>`;
    const now = Date.now(), active = !!o.now, useAur = active && !!AUR;
    const base = active ? Date.UTC(new Date(now).getUTCFullYear(), new Date(now).getUTCMonth(), new Date(now).getUTCDate()) : isoDay(o.start);
    const ph = physics(g, base, useAur), bands = opBands(o), lines = [], sp = pathStats(g.az, g.km, now, useAur);
    let warn = '';
    if (active && sp.aur != null && sp.aur >= 30) warn = T.polarNow(sp.aur.toFixed(0));
    else if (Math.abs(sp.mag) >= 60) warn = T.polar((sp.mag >= 0 ? 'N' : 'S') + Math.abs(sp.mag).toFixed(0));
    if (active && (AUR ? (sp.aur ?? 0) >= 10 : Math.abs(sp.mag) >= 62)) { const sk = skewSearch(g, o); if (sk) warn += (warn ? '<br>' : '') + T.skewAdv(sk.az.toFixed(0), llToGrid(sk.turn[0], sk.turn[1])); }
    for (const k of ['low', 'mid', 'high']) {
      const bs = GROUPS[k].filter(b => bands.includes(b)); if (!bs.length) continue;
      const lab = `<b>${T[k]}</b> <span class="adv-b">${bs.map(b => b.replace('m', '')).join('·')}m</span>`;
      let w = windows(ph[k].map((x, h) => x.v === 2 ? h : -1).filter(h => h >= 0)), extra = '';
      if (k === 'low' && w && ph.low.some(x => x.v === 2 && x.lp)) {
        const lpH = ph.low.map((x, h) => x.v === 2 && x.lp ? h : -1).filter(h => h >= 0), spH = ph.low.map((x, h) => x.v === 2 && !x.lp ? h : -1).filter(h => h >= 0);
        w = [spH.length ? `${T.sp} ${windows(spH)}` : '', `<b>${T.lp}</b> ${windows(lpH)}`].filter(Boolean).join(T.sepL);
      }
      if (!w && k === 'high') { const w1 = windows(ph.high.map((x, h) => x.v >= 1 ? h : -1).filter(h => h >= 0)); if (w1) { w = w1; extra = T.ctrl; } }
      lines.push(`${lab}　${w || (k === 'low' ? (ph.low.some(x => x.blk) ? T.aurLow : T.noLow) : k === 'high' ? T.noHigh : T.noMid)}${extra}`);
    }
    const rec = record(o, bands); let recHtml = '', agree = [];
    if (rec) {
      if (rec.out.length) {
        recHtml = `<div class="adv-h">${T.rec(SUMMARY.days, rec.lab)}</div>` + rec.out.map(x => `<b>${x.b}</b>　${windows(x.hs)}`).join('<br>');
        for (const x of rec.out) { const p = ph[Object.keys(GROUPS).find(k => GROUPS[k].includes(x.b))]; const hs = x.hs.filter(h => p[h].v === 2); if (hs.length) agree.push(`<b>${x.b}</b> ${windows(hs)}`); }
      } else if (!rec.lab) recHtml = `<div class="adv-h">${T.rec(SUMMARY.days, '')}</div>${T.recNone}`;
    }
    return (agree.length ? `<div class="adv-best">${T.agree}：${agree.slice(0, 3).join(T.sepL)} <span class="adv-n">${rec.lab ? T.agreeNear : T.agreeWhy}</span></div>` : '') +
      (warn ? `<div class="adv-w">${warn}</div>` : '') +
      `<div class="adv-h">${active ? T.physNow : T.physOn(T.day(base))}</div>${lines.join('<br>')}` + (recHtml ? `<div class="adv-r">${recHtml}</div>` : '');
  }
  // 明細欄：自局からの方位と、目安
  function renderList() {
    for (const el of document.querySelectorAll('.azl[data-i]')) {
      const o = OPS[+el.dataset.i]; if (o.lat == null) { el.innerHTML = ''; continue; }
      const g = bearingDist(STATION.lat, STATION.lon, o.lat, o.lon);
      el.innerHTML = g.km < 300 ? '' : T.az(STATION.name, g.az.toFixed(0), ((g.az + 180) % 360).toFixed(0), kmStr(g.km));
    }
    for (const el of document.querySelectorAll('.adv[data-i]')) { try { el.innerHTML = advice(OPS[+el.dataset.i]); } catch (e) { el.innerHTML = ''; } }
    document.querySelectorAll('.adv-tt').forEach(e => e.textContent = T.advTitle);
    document.querySelectorAll('.adv-t .vf').forEach(e => e.textContent = T.vf);
    document.querySelectorAll('button.mapbtn').forEach(e => e.textContent = T.show);
  }

  // ---- 地図の欄の文言（言語が変わったら書き直す）
  function renderLabels() {
    $('mapTitle').textContent = T.title; $('mapLead').textContent = T.lead; $('myLab').textContent = T.myLab; $('gridGo').textContent = T.go; $('opLab').textContent = T.opLab;
    const L = T.leg, sw = (st, t) => `<span><i style="${st}"></i>${t}</span>`;
    $('legend').innerHTML = [sw('background:#e05555;border-radius:50%;width:10px;height:10px', L[0]), sw('border:2px solid #c8d0da;border-radius:50%;width:10px;height:10px;box-sizing:border-box', L[1]),
      sw('background:#d8b14a', L[2]), sw('background:repeating-linear-gradient(90deg,#7fd3c6 0 4px,transparent 4px 7px)', L[3]), sw('background:repeating-linear-gradient(90deg,#c77dff 0 3px,transparent 3px 6px)', L[4]),
      sw('background:#05080d', L[5]), sw('background:#3a3550', L[6]), sw('background:rgba(80,220,140,.8)', L[7]), sw('background:rgba(240,90,80,.8)', L[8]),
      sw('background:rgb(255,140,60)', L[9]), sw('background:repeating-linear-gradient(90deg,rgb(255,90,90) 0 5px,transparent 5px 8px)', L[10])].join('');
    const now = Date.now(), cur = $('opSel').value;
    $('opSel').innerHTML = `<option value="">${T.opNone}</option>` + OPS.map((o, i) => o.lat == null ? '' :
      `<option value="${i}">${esc(o.call)}　${esc(o.entity)}（${o.now ? T.opNow : T.opUp(Math.max(0, Math.ceil((isoDay(o.start) - now) / 864e5)))}）</option>`).join('');
    $('opSel').value = SEL != null ? String(SEL) : cur; btns();
  }
  function btns() {
    const set = (id, on, t) => { const b = $(id); b.textContent = (on ? '▼ ' : '▶ ') + t; b.classList.toggle('on', on); };
    set('magBtn', MAG_ON, T.magBtn); set('drapBtn', DRAP_ON, T.drapBtn); set('stormBtn', STORM_ON, T.stormBtn); set('upBtn', SHOW_UP, T.upBtn);
    const notes = [];
    if (MAG_ON) notes.push(T.magNote);
    if (DRAP_ON) notes.push(DRAP ? T.drapNote(DRAP.valid, drapMax(), DRAP.xr) : T.drapNA);
    if (STORM_ON) { const se = stormEdge(); notes.push(se ? T.stormNote(se) : T.stormNA); }
    $('layerNote').innerHTML = notes.map(x => `<div>${x}</div>`).join('');
  }

  // ---- 地図
  function groups() {
    const now = Date.now(), g = new Map();
    OPS.forEach((o, i) => {
      if (o.lat == null) return;
      const up = !o.now && (SHOW_UP && isoDay(o.start) - now <= 14 * 864e5 || i === SEL);
      if (!o.now && !up) return;
      const k = o.lat.toFixed(1) + ',' + o.lon.toFixed(1);
      if (!g.has(k)) g.set(k, { lat: o.lat, lon: o.lon, ops: [], now: false });
      const x = g.get(k); x.ops.push(i); if (o.now) x.now = true;
    });
    return [...g.values()];
  }
  function drawMap() {
    const cv = $('dxMap'); if (!cv || !STATION) return;
    const W = cv.clientWidth || 320, dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(W * dpr); cv.height = Math.round(W * dpr); const c = cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const S = { cx: W / 2, cy: W / 2, R: W / 2 - 22 }, fs = W < 360 ? 9 : 11, now = Date.now();
    const pr = (lat, lon) => { const g = bearingDist(STATION.lat, STATION.lon, lat, lon), r = g.km / HALF * S.R; return [S.cx + r * Math.sin(g.az * RAD), S.cy - r * Math.cos(g.az * RAD)]; };
    const pa = (az, km) => { const r = Math.min(km, HALF) / HALF * S.R; return [S.cx + r * Math.sin(az * RAD), S.cy - r * Math.cos(az * RAD)]; };
    const poly = pts => { c.beginPath(); let pen = false; for (let i = 0; i < pts.length; i++) { const p = pts[i]; if (i && Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > S.R * 0.35) pen = false; if (!pen) { c.moveTo(p[0], p[1]); pen = true; } else c.lineTo(p[0], p[1]); } c.stroke(); };
    c.clearRect(0, 0, W, W); c.save(); c.beginPath(); c.arc(S.cx, S.cy, S.R, 0, 2 * Math.PI); c.fillStyle = '#163250'; c.fill(); c.clip();
    if (LAND) for (const ring of LAND) {
      const pts = ring.map(([lo, la]) => pr(la, lo)); let jump = false, pen = false; c.beginPath();
      for (let i = 0; i < pts.length; i++) { const p = pts[i]; if (i && Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > S.R * 0.35) { pen = false; jump = true; } if (!pen) { c.moveTo(p[0], p[1]); pen = true; } else c.lineTo(p[0], p[1]); }
      if (!jump) { c.closePath(); c.fillStyle = '#355a3e'; c.fill(); }
      c.strokeStyle = '#7a9a80'; c.lineWidth = .7; c.stroke();
    }
    // 昼夜・D層の吸収・オーロラ帯（ナウキャストと同じ色と順）
    const N = 170, off = document.createElement('canvas'); off.width = N; off.height = N; const oc = off.getContext('2d'), img = oc.createImageData(N, N);
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      const dx = (i + .5) / N * 2 - 1, dy = (j + .5) / N * 2 - 1, rr = Math.hypot(dx, dy); if (rr > 1) continue;
      const az = Math.atan2(dx, -dy) / RAD, [la, lo] = dest(STATION.lat, STATION.lon, (az + 360) % 360, rr * HALF), e = sunElev(la, lo, now), k = (j * N + i) * 4;
      let r = 0, g = 0, b = 0, a = 0;
      if (e < -6) { r = 2; g = 5; b = 12; a = 175; } else if (e < 0) { r = 40; g = 34; b = 80; a = Math.round(70 + (-e / 6) * 70); }
      if (DRAP_ON && DRAP) { const v = drapAt(la, lo); if (v != null && v >= 1) { const s3 = v >= 10 ? [220, 70, 170, 170] : v >= 5 ? [255, 120, 40, 150] : [255, 176, 90, Math.round(70 + v * 12)]; r = s3[0]; g = s3[1]; b = s3[2]; a = Math.max(a, s3[3]); } }
      const au = aurAt(la, lo);
      if (au != null && au >= 10) { const st = au >= 30; r = st ? 240 : 80; g = st ? 90 : 220; b = st ? 80 : 140; a = Math.max(a, st ? 190 : Math.round(70 + au * 3)); }
      img.data[k] = r; img.data[k + 1] = g; img.data[k + 2] = b; img.data[k + 3] = a;
    }
    oc.putImageData(img, 0, 0); c.drawImage(off, S.cx - S.R, S.cy - S.R, 2 * S.R, 2 * S.R);
    // 地磁気緯度線（双極子近似）
    if (MAG_ON) for (const Lm of [-70, -60, -30, 0, 30, 60, 70]) {
      const pts = []; for (let a = 0; a <= 360; a += 2) { const [la, lo] = dest(GMPOLE.lat, GMPOLE.lon, a, (90 - Lm) * RAD * EARTH); pts.push(pr(la, lo)); }
      const key = Math.abs(Lm) === 60;
      c.setLineDash(key ? [6, 3] : [2, 4]); c.strokeStyle = key ? 'rgba(240,138,75,.95)' : 'rgba(225,225,235,.6)'; c.lineWidth = key ? 1.7 : 1; poly(pts); c.setLineDash([]);
      let best = null; for (const p of pts) { const d = Math.hypot(p[0] - S.cx, p[1] - S.cy); if (d < S.R * 0.92 && d > S.R * 0.15 && (!best || d < best.d)) best = { p, d }; }
      if (best) { c.font = 'bold ' + (fs - 1) + 'px sans-serif'; c.fillStyle = key ? '#f08a4b' : '#e1e1eb'; c.textAlign = 'left'; c.fillText(Lm === 0 ? '0°' : (Lm > 0 ? 'N' : 'S') + Math.abs(Lm) + '°', best.p[0] + 4, best.p[1] - 3); }
    }
    // 嵐の広がり（オーロラ帯の縁の見込み）
    const se = STORM_ON ? stormEdge() : null, storm = se && se.show;
    if (storm) for (const Lm of [se.edge, -se.edge]) {
      const pts = []; for (let a = 0; a <= 360; a += 2) { const [la, lo] = dest(GMPOLE.lat, GMPOLE.lon, a, (90 - Lm) * RAD * EARTH); pts.push(pr(la, lo)); }
      c.setLineDash([7, 4]); c.strokeStyle = 'rgba(255,90,90,.95)'; c.lineWidth = 1.8; poly(pts); c.setLineDash([]);
    }
    c.setLineDash([3, 4]); c.strokeStyle = '#33404e'; c.lineWidth = 1;
    for (const km of [5000, 10000, 15000]) { c.beginPath(); c.arc(S.cx, S.cy, km / HALF * S.R, 0, 2 * Math.PI); c.stroke(); }
    c.setLineDash([]);
    // 選んだ運用までの伝搬経路（短経路・長経路・ずらした方位）
    let R = null;
    if (SEL != null && OPS[SEL] && OPS[SEL].lat != null) {
      const o = OPS[SEL]; R = route(o); const { g, sk } = R, t = pa(g.az, g.km), e1 = pa((g.az + 180) % 360, HALF), e2 = pa(g.az, HALF);
      if (sk) { c.strokeStyle = '#c77dff'; c.lineWidth = 2.2; c.setLineDash([3, 3]); poly(sk.pts.map(([la, lo]) => pr(la, lo))); c.setLineDash([]);
        const q = pr(sk.turn[0], sk.turn[1]); c.fillStyle = '#c77dff'; c.beginPath(); c.arc(q[0], q[1], 3.5, 0, 2 * Math.PI); c.fill(); }
      c.lineWidth = 1.8; c.setLineDash([6, 4]); c.strokeStyle = '#7fd3c6';
      c.beginPath(); c.moveTo(S.cx, S.cy); c.lineTo(e1[0], e1[1]); c.stroke(); c.beginPath(); c.moveTo(e2[0], e2[1]); c.lineTo(t[0], t[1]); c.stroke(); c.setLineDash([]);
      c.strokeStyle = '#d8b14a'; c.lineWidth = 3; c.beginPath(); c.moveTo(S.cx, S.cy); c.lineTo(t[0], t[1]); c.stroke();
      if (storm) { const red = (az2, len) => { c.strokeStyle = 'rgba(255,70,70,.95)'; c.lineWidth = 4.5; c.beginPath(); let pen = false, prev = null;
          for (let x = 0; x <= len; x += 100) { const [la, lo] = dest(STATION.lat, STATION.lon, az2, x), q = pr(la, lo), inZ = Math.abs(magLat(la, lo)) >= se.edge;
            if (prev && Math.hypot(q[0] - prev[0], q[1] - prev[1]) > S.R * 0.35) pen = false; if (inZ) { if (!pen) { c.moveTo(q[0], q[1]); pen = true; } else c.lineTo(q[0], q[1]); } else pen = false; prev = q; } c.stroke(); };
        red(g.az, g.km); red((g.az + 180) % 360, 2 * HALF - g.km); }
      // 短経路の上で地磁気緯度が最も高くなる地点
      let best = 0, bx = 0; for (let x = 0; x <= g.km; x += 100) { const [la, lo] = dest(STATION.lat, STATION.lon, g.az, x), m = Math.abs(magLat(la, lo)); if (m > best) { best = m; bx = x; } }
      const mp = pa(g.az, bx); c.strokeStyle = '#f08a4b'; c.lineWidth = 2; c.beginPath(); c.arc(mp[0], mp[1], 5, 0, 2 * Math.PI); c.stroke();
      c.fillStyle = '#f08a4b'; c.font = 'bold ' + fs + 'px sans-serif'; c.textAlign = 'left'; c.fillText(`${R.sp.mag >= 0 ? 'N' : 'S'}${Math.abs(R.sp.mag).toFixed(0)}°`, mp[0] + 7, mp[1] - 5);
    }
    // 運用の印とコールサイン（近くに置けなければ少し離して引き出し線でつなぐ）
    const G = groups(), boxes = [], hit = b => boxes.some(x => b.x < x.x + x.w && b.x + b.w > x.x && b.y < x.y + x.h && b.y + b.h > x.y);
    const ptsG = G.map(x => ({ ...x, p: pr(x.lat, x.lon) }));
    for (const x of ptsG) boxes.push({ x: x.p[0] - 5, y: x.p[1] - 5, w: 10, h: 10 });
    boxes.push({ x: S.cx - 6, y: S.cy - 6, w: 70, h: 22 });
    HITS = [];
    ptsG.sort((a, b) => (b.ops.includes(SEL) - a.ops.includes(SEL)) || (b.now - a.now));
    for (const x of ptsG) {
      const [px, py] = x.p, sel = x.ops.includes(SEL);
      c.beginPath(); c.arc(px, py, sel ? 6.5 : 5, 0, 2 * Math.PI);
      if (x.now) { c.fillStyle = '#e05555'; c.fill(); c.strokeStyle = '#fff'; c.lineWidth = sel ? 2.2 : 1.3; c.stroke(); }
      else { c.fillStyle = 'rgba(10,14,20,.5)'; c.fill(); c.strokeStyle = sel ? '#fff' : '#c8d0da'; c.lineWidth = 1.8; c.stroke(); }
      HITS.push({ x: px, y: py, ops: x.ops });
      const calls = [...new Set(x.ops.map(i => OPS[i].call))], txt = calls.length > 2 ? calls.slice(0, 2).join('·') + '…' : calls.join('·');
      c.font = 'bold ' + fs + 'px sans-serif'; const w = c.measureText(txt).width + 6, h = fs + 4;
      const cand = [[8, -h / 2], [-8 - w, -h / 2], [-w / 2, -h - 7], [-w / 2, 7], [8, -h - 4], [-8 - w, -h - 4], [8, 4], [-8 - w, 4]];
      for (const r of [26, 40]) for (let a = 0; a < 360; a += 30) { const ox = r * Math.cos(a * RAD), oy = r * Math.sin(a * RAD); cand.push([ox >= 0 ? ox : ox - w, oy - h / 2]); }
      for (const [ox, oy] of cand) {
        const b = { x: px + ox, y: py + oy, w, h };
        if (b.x < 2 || b.x + w > W - 2 || hit(b)) continue;
        if (Math.hypot(Math.max(Math.abs(b.x - S.cx), Math.abs(b.x + w - S.cx)), Math.max(Math.abs(b.y - S.cy), Math.abs(b.y + h - S.cy))) > S.R + 4) continue;
        boxes.push(b);
        if (Math.hypot(ox, oy) > 22) { const lx = Math.max(b.x, Math.min(px, b.x + w)), ly = Math.max(b.y, Math.min(py, b.y + h)); c.strokeStyle = 'rgba(230,235,240,.7)'; c.lineWidth = 1; c.beginPath(); c.moveTo(px, py); c.lineTo(lx, ly); c.stroke(); }
        c.fillStyle = sel ? 'rgba(120,20,20,.9)' : 'rgba(10,14,20,.78)'; c.fillRect(b.x, b.y, w, h);
        c.fillStyle = x.now || sel ? '#ffffff' : '#c8d0da'; c.textAlign = 'left'; c.fillText(txt, b.x + 3, b.y + h - 4); break;
      }
    }
    c.restore();
    c.strokeStyle = '#5a6573'; c.lineWidth = 1.2; c.beginPath(); c.arc(S.cx, S.cy, S.R, 0, 2 * Math.PI); c.stroke();
    c.textAlign = 'center'; c.font = fs + 'px sans-serif';
    const rim = (a, col, bold) => { c.fillStyle = col; c.font = (bold ? 'bold ' : '') + fs + 'px sans-serif'; c.fillText(a === 0 && !bold ? 'N' : Math.round(a) + '°', S.cx + (S.R + 12) * Math.sin(a * RAD), S.cy - (S.R + 12) * Math.cos(a * RAD) + 3); };
    for (let a = 0; a < 360; a += 30) rim(a, a === 0 ? '#d8b14a' : css('--sub'), false);
    if (R) { rim(R.g.az, '#d8b14a', true); if (R.sk) rim(R.sk.az, '#c77dff', true); }
    c.fillStyle = '#d8b14a'; c.beginPath(); c.arc(S.cx, S.cy, 4, 0, 2 * Math.PI); c.fill(); c.font = 'bold ' + fs + 'px sans-serif'; c.textAlign = 'left'; c.fillText(STATION.name, S.cx + 6, S.cy + 14);
    $('mapTime').textContent = T.at(now);
    if (SEL != null && R) $('mapInfo').innerHTML = T.info(OPS[SEL], R) + `　<a href="#op${SEL}">${T.toList}</a>`;
    else $('mapInfo').innerHTML = G.some(x => x.now) ? T.hint : T.noneActive;
  }
  function select(i, scrollMap) {
    SEL = i == null || isNaN(i) ? null : i; $('opSel').value = SEL != null ? String(SEL) : ''; drawMap();
    if (scrollMap) $('mapCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  // 自局：コールサインかグリッド。日本国内なら日本語、国外なら英語で表示する
  async function setStation(userSet) {
    const raw = ($('myGrid').value || '').trim().toUpperCase().replace(/\s+/g, ''); let r = null, note = '';
    if (KNOWN[raw]) { const k = gridToLL(KNOWN[raw]); r = { name: raw, lat: k.lat, lon: k.lon }; note = 'known'; }
    else { const g = gridToLL(raw); if (g) { r = { name: g.grid, lat: g.lat, lon: g.lon }; note = 'grid'; } }
    if (!r && /^[A-Z0-9\/]{3,15}$/.test(raw)) {
      try { if (!CTY) CTY = await fetch(IONO + 'cty.json', { cache: 'no-store' }).then(x => { if (!x.ok) throw 0; return x.json(); }); const e = lookupCall(raw); if (e) { r = { name: raw, lat: e.lat, lon: e.lon, ent: e.name }; note = 'call'; } }
      catch (e) { note = 'ctyfail'; }
    }
    const ok = !!r;
    if (!r) { const d = gridToLL('PM95'); r = { name: 'PM95', lat: d.lat, lon: d.lon }; }
    STATION = r;
    if (ok && userSet) LS('dx.station', raw);
    LG = ok && (userSet || LS('dx.station')) ? (isJapan(r.lat, r.lon) ? 'ja' : 'en') : PAGE_LANG;
    T = LG === 'en' ? TE : TJ;
    $('stInfo').innerHTML = !ok ? (note === 'ctyfail' ? T.ctyFail : T.bad(raw)) :
      T.centre(r.name, note === 'known' ? T.knownNote(KNOWN[raw]) : note === 'grid' ? T.gridNote(r.name) : T.callNote(r.ent, llToGrid(r.lat, r.lon)));
    $('myGrid').value = raw || 'PM95';
    renderLabels();
  }
  async function refresh(userSet) { await setStation(userSet); drawMap(); renderList(); }

  $('dxMap').addEventListener('click', ev => {
    const r = ev.target.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    let best = null; for (const h of HITS) { const d = Math.hypot(h.x - x, h.y - y); if (d < 16 && (!best || d < best.d)) best = { d, h }; }
    if (!best) return; const k = best.h.ops, cur = k.indexOf(SEL); select(k[(cur + 1) % k.length], false);
  });
  $('opSel').addEventListener('change', e => select(e.target.value === '' ? null : +e.target.value, false));
  document.querySelectorAll('button.mapbtn[data-i]').forEach(b => b.addEventListener('click', () => select(+b.dataset.i, true)));
  $('gridGo').addEventListener('click', () => refresh(true));
  $('myGrid').addEventListener('keydown', e => { if (e.key === 'Enter') { e.target.blur(); refresh(true); } });
  const tog = (id, key, get, set) => $(id).addEventListener('click', () => { set(!get()); LS(key, get() ? '1' : '0'); btns(); drawMap(); });
  tog('magBtn', 'dx.mag', () => MAG_ON, v => MAG_ON = v); tog('drapBtn', 'dx.drap', () => DRAP_ON, v => DRAP_ON = v);
  tog('stormBtn', 'dx.storm', () => STORM_ON, v => STORM_ON = v); tog('upBtn', 'dx.showUp', () => SHOW_UP, v => SHOW_UP = v);
  const fh = () => { const f = document.querySelector('.filters'); if (f) document.documentElement.style.setProperty('--fh', f.offsetHeight + 'px'); };
  window.addEventListener('resize', () => { drawMap(); fh(); }); fh();

  const getJ = u => fetch(u, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  const avg = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  // いまの宇宙天気（オーロラ・D層の吸収・太陽風）。10分ごとに読み直して地図を描き直す
  function loadSpace() {
    const rt = (d, cols) => { const out = rows(d).filter(r => r && r.active === true && r[cols[0]] != null).map(r => [Date.parse(String(r.time_tag).replace(' ', 'T').slice(0, 19) + 'Z'), parseFloat(r[cols[0]])]).filter(r => !isNaN(r[0]) && !isNaN(r[1])).sort((a, b) => a[0] - b[0]);
      if (!out.length) return out; const e = out[out.length - 1][0]; return out.filter(r => r[0] > e - 2 * 3600e3); };
    const tail = a => { if (!a.length) return []; const e = a[a.length - 1][0]; return a.filter(r => r[0] > e - 1800e3).map(r => r[1]); };
    return Promise.allSettled([
      getJ(NOAA + '/json/ovation_aurora_latest.json').then(d => { AUR = parseAur(d); }),
      fetch(NOAA + '/text/drap_global_frequencies.txt', { cache: 'no-store' }).then(r => r.ok ? r.text() : null).then(t => { if (t) DRAP = parseDrap(t); }),
      Promise.all([getJ(NOAA + '/json/rtsw/rtsw_mag_1m.json'), getJ(NOAA + '/json/rtsw/rtsw_wind_1m.json'), getJ(NOAA + '/products/noaa-planetary-k-index.json').catch(() => null)]).then(([m, w, k]) => {
        const mag = rt(m, ['bz_gsm']), wind = rt(w, ['proton_speed']), kp = rows(k).map(r => parseFloat(r.Kp ?? r.kp)).filter(x => !isNaN(x));
        SW = { bz30: mag.length ? avg(tail(mag)) : null, sp: wind.length ? avg(tail(wind)) : null, kp: kp.length ? kp[kp.length - 1] : null, south: southMin(mag) };
      }),
    ]).then(() => { btns(); drawMap(); });
  }
  (async function init() {
    const s = LS('dx.station'); if (s) $('myGrid').value = s;
    await setStation(false);
    document.querySelectorAll('.adv[data-i]').forEach(el => el.textContent = T.loading);
    drawMap(); renderList();
    getJ(IONO + 'land.json').then(d => { LAND = d.rings; drawMap(); }).catch(() => {});
    await Promise.allSettled([
      loadSpace(),
      getJ(NOAA + '/products/10cm-flux-30-day.json').then(d => { const a = rows(d).filter(r => r.flux != null); if (a.length) SFI = parseFloat(a[a.length - 1].flux); }),
      getJ(SUMMARY_URL).then(d => { SUMMARY = d; }),
    ]);
    renderList(); drawMap();
    setInterval(() => { if (!document.hidden) loadSpace(); }, 10 * 60e3);
  })();
})();
'''


def main():
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read() if len(sys.argv) > 1 else fetch()
    now = datetime.now(timezone.utc)
    today = now.date()
    ops = [o for o in parse(text) if o["end"] >= today and o["start"] <= today + timedelta(days=DAYS)]
    ops.sort(key=lambda o: (not (o["start"] <= today <= o["end"]), o["start"], o["end"]))
    cty = fetch_cty()
    for o in ops:
        loc = locate(o, cty)
        o["ent"], o["lat"], o["lon"] = loc if loc else (None, None, None)
    if not ops and len(sys.argv) == 1:
        sys.exit("予定を1件も読み取れませんでした（ページの形式が変わった可能性があります）。前回のページを残します。")
    jst = now + timedelta(hours=9)
    updated = f"{jst:%Y-%m-%d %H:%M} JST（{now:%H:%M} UTC）"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(ops, today, updated))
    updated_en = f"{now:%Y-%m-%d %H:%M} UTC"
    with open(OUT_EN, "w", encoding="utf-8") as f:
        f.write(render(ops, today, updated_en, "en"))
    print(f"{len(ops)}件を書き出しました: {OUT}、{OUT_EN}")


if __name__ == "__main__":
    main()
