#!/usr/bin/env python3
"""Render the audit report: verdicts.json + checklist.json + shots/ -> report.html (one self-contained file).

verdicts.json is draft.json after the agent filled every item's status, evidence, why and recommendation.
Each screenshot is embedded once, so the file stays small enough to email.

Usage:
  python render.py --out ./sale-audit/store.com            # English labels
  python render.py --out ./sale-audit/store.com --lang uk  # Ukrainian labels
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
CHECKLIST = json.loads((HERE.parent / "checklist.json").read_text(encoding="utf-8"))
ORDER = ["missing", "partial", "done", "cannot_verify", "not_applicable", "info"]
L = {
    "en": {"title": "Sale readiness audit", "missing": "Missing", "partial": "Partial", "done": "Done", "cannot_verify": "Can't verify",
           "not_applicable": "N/A", "info": "Fact", "evidence": "What we saw", "why": "Why it matters", "rec": "What to do",
           "fix": "Fix first", "all": "All checks", "walk": "How the store was walked", "checks": "checks", "passed": "pass",
           "of": "of", "measurable": "checks that apply", "by": "Audit by", "filter_all": "All", "none": "Nothing missing or partial."},
    "uk": {"title": "Аудит готовності до розпродажу", "missing": "Немає", "partial": "Частково", "done": "Є", "cannot_verify": "Не перевірити",
           "not_applicable": "Не стосується", "info": "Факт", "evidence": "Що побачили", "why": "Чому це важливо", "rec": "Що зробити",
           "fix": "Виправити першим", "all": "Усі перевірки", "walk": "Як проходили магазин", "checks": "перевірок", "passed": "пройдено",
           "of": "з", "measurable": "перевірок, що стосуються магазину", "by": "Аудит від", "filter_all": "Усі", "none": "Нічого не бракує."},
}

CSS = """
:root{--bg:#f6f6f4;--card:#fff;--ink:#1c1c1f;--mute:#6a6a70;--line:#e3e3df;--miss:#c0392b;--part:#c27c0e;--done:#1e8e3e;--na:#8a8a8f;--cv:#5b6bbf;--info:#4a7c8c;--brand:#F3492C}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--ink:#ececee;--mute:#a0a0a8;--line:#2e2e33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:34px 0 10px}
.mute{color:var(--mute)}.score{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:118px}
.stat b{font-size:22px;display:block}.big{font-size:40px;font-weight:700;line-height:1}
.chip{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;color:#fff;white-space:nowrap;vertical-align:1px}
.missing{background:var(--miss)}.partial{background:var(--part)}.done{background:var(--done)}.cannot_verify{background:var(--cv)}.not_applicable{background:var(--na)}.info{background:var(--info)}
.fix{background:var(--card);border:1px solid var(--line);border-radius:10px}.fix div{padding:10px 14px;border-top:1px solid var(--line)}.fix div:first-child{border-top:0}
details.blk{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:10px 0}details.blk>summary{cursor:pointer;padding:12px 14px;font-weight:600}
.item{border-top:1px solid var(--line);padding:12px 14px}.item h3{font-size:15px;margin:0 0 6px}.kv{margin:4px 0}.kv b{color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase;margin-right:6px}
.thumbs{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.thumbs img{height:150px;border:1px solid var(--line);border-radius:6px;cursor:zoom-in}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.filters button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:4px 12px;cursor:pointer;font:inherit;font-size:13px}
.filters button.on{background:var(--ink);color:var(--bg)}#zoom{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:flex-start;justify-content:center;overflow:auto;z-index:9}
#zoom img{max-width:96vw;margin:2vh 0}footer{margin-top:40px;color:var(--mute);font-size:13px}footer a{color:var(--brand)}
@media(max-width:640px){.thumbs img{height:110px}.big{font-size:32px}}
"""
JS = """
document.querySelectorAll('img[data-k]').forEach(i=>i.src=IMG[i.dataset.k]);
const z=document.getElementById('zoom');document.querySelectorAll('.thumbs img').forEach(i=>i.onclick=()=>{z.innerHTML='<img src="'+i.src+'">';z.style.display='flex'});z.onclick=()=>z.style.display='none';
document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.filters button').forEach(x=>x.classList.remove('on'));b.classList.add('on');
const s=b.dataset.s;document.querySelectorAll('.item').forEach(it=>it.style.display=(s==='all'||it.dataset.s===s)?'':'none')});
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def data_url(p: Path) -> str:
    from PIL import Image
    im = Image.open(p).convert("RGB")
    if im.width > 760:
        im = im.resize((760, round(im.height * 760 / im.width)))
    if im.height > 1600:
        im = im.crop((0, 0, im.width, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=62)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="en", help="Labels: en or uk (verdict text is used as written)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = Path(args.out)
    t = L.get(args.lang, L["en"])
    v = json.loads((out / "verdicts.json").read_text(encoding="utf-8"))
    meta = {i["id"]: i for i in CHECKLIST["items"]}
    rows = []
    unset = []
    for r in v["items"]:
        m = meta.get(r["id"], {})
        st = r.get("status") if r.get("status") in ORDER else None
        if st is None:
            unset.append(r["id"])
            st = "cannot_verify"
        rows.append({**m, **r, "status": st, "why": r.get("why_it_matters") or m.get("why", "")})
    if unset:
        print(f"WARNING: no status for {', '.join(unset)} - shown as can't verify. Fill them in verdicts.json and render again.")

    imgs: dict[str, str] = {}

    def thumbs(r):
        names = [n for n in (r.get("screenshots") or []) if n and (out / "shots" / n).exists()][:3]
        for n in names:
            if n not in imgs:
                imgs[n] = data_url(out / "shots" / n)
        return "".join(f"<img alt='{esc(n)}' title='{esc(n)}' data-k='{esc(n)}'>" for n in names)

    c = {s: sum(1 for r in rows if r["status"] == s) for s in ORDER}
    applies = c["done"] + c["partial"] + c["missing"]
    gaps = [r for r in rows if r["status"] in ("missing", "partial")]
    gaps.sort(key=lambda r: (r["status"] != "missing", list(CHECKLIST["blocks"]).index(r["block"]) if r.get("block") in CHECKLIST["blocks"] else 99))
    fix = "".join(f"<div><span class='chip {r['status']}'>{esc(t[r['status']])}</span> <b>{esc(r['id'])} · {esc(r['title'])}</b>"
                  f"<div class='mute' style='padding:2px 0 0;border:0'>{esc(r.get('recommendation'))}</div></div>" for r in gaps) or f"<div>{t['none']}</div>"
    blocks = []
    for b, bname in CHECKLIST["blocks"].items():
        its = [r for r in rows if r.get("block") == b]
        if not its:
            continue
        bc = {s: sum(1 for r in its if r["status"] == s) for s in ORDER}
        head = " · ".join(f"{t[s]} {bc[s]}" for s in ORDER if bc[s])
        body = []
        for r in sorted(its, key=lambda r: ORDER.index(r["status"])):
            th = thumbs(r)
            body.append(f"<div class='item' data-s='{r['status']}'><h3><span class='chip {r['status']}'>{esc(t[r['status']])}</span> {esc(r['id'])} · {esc(r['title'])}</h3>"
                        f"<div class='kv'><b>{t['evidence']}</b>{esc(r.get('evidence'))}</div>"
                        + (f"<div class='kv'><b>{t['why']}</b>{esc(r['why'])}</div>" if r["status"] in ("missing", "partial") and r.get("why") else "")
                        + (f"<div class='kv'><b>{t['rec']}</b>{esc(r.get('recommendation'))}</div>" if r.get("recommendation") else "")
                        + (f"<div class='thumbs'>{th}</div>" if th else "") + "</div>")
        blocks.append(f"<details class='blk' open><summary>{esc(b)}. {esc(bname)} <span class='mute'>— {head}</span></summary>{''.join(body)}</details>")
    plan = v.get("plan") or {}
    walked = [f"product: {esc((plan.get('product') or {}).get('url'))}", f"category: {esc(plan.get('category'))}", f"FAQ: {esc(plan.get('faq'))}",
              f"other language: {esc((plan.get('other_language') or {}).get('href'))}"]
    errs = [f"{d}: {esc(e)}" for d, es in (v.get("walk_errors") or {}).items() for e in es]
    filters = f"<div class='filters'><button class='on' data-s='all'>{t['filter_all']}</button>" + "".join(
        f"<button data-s='{s}'>{esc(t[s])} ({c[s]})</button>" for s in ORDER if c[s]) + "</div>"
    stats = f"<div class='stat'><span class='big'>{c['done']}</span> <span class='mute'>{t['passed']} {t['of']} {applies} {t['measurable']}</span></div>" + "".join(
        f"<div class='stat'><b>{c[s]}</b><span class='chip {s}'>{esc(t[s])}</span></div>" for s in ORDER if c[s])
    host = v["site"].split("//")[-1].strip("/")
    page = f"""<!doctype html><html lang="{esc(args.lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{esc(host)} — {t['title']}</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{esc(host)} — {t['title']}</h1><div class="mute">{esc(v.get('walked_utc'))} UTC · {len(rows)} {t['checks']} · desktop 1440×900 + mobile 390×844</div>
<div class="score">{stats}</div>
<h2>{t['fix']}</h2><div class="fix">{fix}</div>
<h2>{t['all']}</h2>{filters}{''.join(blocks)}
<h2>{t['walk']}</h2><div class="mute">{'<br>'.join(walked + errs)}</div>
<footer>{t['by']} <a href="https://claspo.io/?utm_source=sale-readiness-audit&utm_medium=report">Claspo</a> · sale-readiness-audit plugin</footer>
</div><div id="zoom"></div><script>const IMG={json.dumps(imgs)};{JS}</script></body></html>"""
    (out / "report.html").write_text(page, encoding="utf-8")
    print(f"report.html: {len(rows)} checks ({', '.join(f'{s} {n}' for s, n in c.items() if n)}), {(out / 'report.html').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
