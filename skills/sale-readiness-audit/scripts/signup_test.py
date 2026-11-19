#!/usr/bin/env python3
"""Test signup on the store's own signup form, with the tester's own email. Run only with the store owner's consent.

Finds the signup form a first-time visitor gets (homepage, then a product page), records the consent text
next to the fields, submits the tester's email (never a phone number: a phone step is only recorded), reads
the thank-you step (code shown? "check your email"?), then opens the homepage again with the same browser
storage to see whether a subscriber still gets the form. With --code, it applies that code in a Shopify cart
and reads /cart.js to see whether a discount was applied.

Writes <out>/signup.json and screenshots into <out>/shots/. Run walk.py first (it reads walk.json for the
store's origin and a product page).

Usage:
  python signup_test.py --out ./sale-audit/store.com --email me+test@mystore.com
  python signup_test.py --out ./sale-audit/store.com --code WELCOME10       # only check a code in the cart
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, quote

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from walk import DEVICES, JS, COOKIE_JS  # noqa: E402

CONSENT = re.compile(r"privacy|terms|unsubscribe|consent|agree|msg (&|and) data rates|message frequency|reply stop|marketing (emails|messages)", re.I)
CODE = re.compile(r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9-]{5,20}\b")
CHECK_EMAIL = re.compile(r"check your (email|inbox)|sent (you )?an? (email|code)|on its way to your inbox", re.I)
OPENER = re.compile(r"^(yes|claim|unlock|get|reveal|spin|continue|sign ?up|join|subscribe|i want|count me in|show)", re.I)

FORM_JS = r"""
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`); if (!host) return null;
  const deep = sel => [...host.querySelectorAll(sel), ...[host, ...host.querySelectorAll('*')].filter(n => n.shadowRoot).flatMap(n => [...n.shadowRoot.querySelectorAll(sel)])];
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const inputs = deep('input').filter(vis);
  const email = inputs.find(i => i.type === 'email' || /email/i.test(i.name + ' ' + i.placeholder + ' ' + (i.autocomplete || '')));
  const tel = inputs.find(i => i.type === 'tel' || /phone/i.test(i.name + ' ' + i.placeholder));
  const small = deep('p, span, div, small, label').filter(e => vis(e) && e.children.length < 4).map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(t => t.length > 20 && t.length < 600);
  const buttons = deep('button, [role=button], input[type=submit], a').filter(vis).map(b => (b.innerText || b.value || '').trim()).filter(Boolean).slice(0, 8);
  return {text: (host.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 600), has_email: !!email, has_tel: !!tel, small, buttons};
}
"""

FILL_JS = r"""
([paId, value]) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`); if (!host) return 'no host';
  const deep = sel => [...host.querySelectorAll(sel), ...[host, ...host.querySelectorAll('*')].filter(n => n.shadowRoot).flatMap(n => [...n.shadowRoot.querySelectorAll(sel)])];
  const email = deep('input').find(i => i.type === 'email' || /email/i.test(i.name + ' ' + i.placeholder + ' ' + (i.autocomplete || '')));
  if (!email) return 'no email field';
  email.focus();
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(email, value);
  email.dispatchEvent(new Event('input', {bubbles: true})); email.dispatchEvent(new Event('change', {bubbles: true}));
  const form = email.closest('form');
  const btn = (form ? [...form.querySelectorAll('button, input[type=submit]')] : deep('button, input[type=submit]'))
    .find(b => !/close|dismiss|no,? thanks|×/i.test((b.innerText || b.value || b.getAttribute('aria-label') || '')));
  if (btn) { btn.click(); return 'clicked: ' + (btn.innerText || btn.value || '').trim().slice(0, 40); }
  if (form && form.requestSubmit) { form.requestSubmit(); return 'form submit'; }
  return 'no button';
}
"""

OPEN_JS = r"""
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`); if (!host) return null;
  const re = /^(yes|claim|unlock|get|reveal|spin|continue|sign ?up|join|subscribe|i want|count me in|show)/i;
  const all = [...host.querySelectorAll('button, [role=button], a'), ...[host, ...host.querySelectorAll('*')].filter(n => n.shadowRoot).flatMap(n => [...n.shadowRoot.querySelectorAll('button, [role=button], a')])];
  const b = all.find(x => re.test((x.innerText || '').trim()));
  if (b) { b.click(); return (b.innerText || '').trim().slice(0, 40); }
  return null;
}
"""


async def find_form(page, seconds=40):
    t0 = time.monotonic()
    answered = False
    while time.monotonic() - t0 < seconds:
        try:
            snap = await page.evaluate(JS["detect"])
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.5)
            continue
        for o in snap["overlays"]:
            if o["kind"] == "capture_form":
                return o
        if not answered and time.monotonic() - t0 > 12:
            answered = True
            try:
                await page.evaluate(COOKIE_JS)
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(0.5)
    return None


async def shot(page, out: Path, name: str):
    try:
        await page.screenshot(path=str(out / "shots" / name), type="jpeg", quality=62)
        return name
    except Exception:  # noqa: BLE001
        return None


async def run(args) -> dict:
    out = Path(args.out)
    walk = json.loads((out / "walk.json").read_text(encoding="utf-8"))
    origin, plan = walk["site"], walk["plan"]
    prev = json.loads((out / "signup.json").read_text(encoding="utf-8")) if (out / "signup.json").exists() else {}
    res: dict = dict(prev) if args.email is None else {"email_used": args.email, "device": args.device}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        if args.email:
            ctx = await browser.new_context(locale="en-US", **DEVICES[args.device])
            page = await ctx.new_page()
            form = None
            for url in [origin] + ([plan["product"]["url"]] if plan.get("product") else []):
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                form = await find_form(page)
                if form:
                    res["form_page"] = url
                    break
            if not form:
                res.update(form_found=False, submitted=False, error="no signup form appeared on the homepage or a product page in 40 s")
            else:
                res["form_found"] = True
                info = await page.evaluate(FORM_JS, form["pa_id"])
                if info and not info["has_email"]:
                    opened = await page.evaluate(OPEN_JS, form["pa_id"])
                    res["opened_with"] = opened
                    await page.wait_for_timeout(2000)
                    info = await page.evaluate(FORM_JS, form["pa_id"]) or info
                res["form_text"] = (info or {}).get("text")
                res["form_shot"] = await shot(page, out, f"{args.device}_signup_form.jpg")
                consent = [t for t in (info or {}).get("small", []) if CONSENT.search(t)]
                res["consent_text"] = consent[0] if consent else None
                if not info or not info["has_email"]:
                    res.update(submitted=False, error="the form has no email field on its first steps (phone only, or a game that needs more clicks)")
                else:
                    how = await page.evaluate(FILL_JS, [form["pa_id"], args.email])
                    res["submit"] = how
                    await page.wait_for_timeout(8000)
                    after = await page.evaluate(FORM_JS, form["pa_id"])
                    if not after:  # the form replaced itself: read whatever capture layer is up now
                        snap = await page.evaluate(JS["detect"])
                        cf = [o for o in snap["overlays"] if o["kind"] in ("capture_form", "other_overlay", "vendor_overlay")]
                        after = {"text": cf[0]["text"], "has_tel": cf[0]["has_tel"], "has_email": cf[0]["has_email"]} if cf else {"text": "", "has_tel": False, "has_email": False}
                    res["after_text"] = after.get("text")
                    res["after_shot"] = await shot(page, out, f"{args.device}_signup_after.jpg")
                    res["submitted"] = not (after.get("has_email") and (after.get("text") or "")[:80] == (res.get("form_text") or "")[:80])
                    codes = [c for c in CODE.findall(after.get("text") or "") if c not in ("BLACK", "FRIDAY")]
                    res["code_shown"] = codes[0] if codes else None
                    res["check_email"] = bool(CHECK_EMAIL.search(after.get("text") or ""))
                    res["asks_phone_next"] = bool(after.get("has_tel"))
                    if res["submitted"]:
                        storage = await ctx.storage_state()
                        c2 = await browser.new_context(locale="en-US", storage_state=storage, **DEVICES[args.device])
                        p2 = await c2.new_page()
                        await p2.goto(origin, wait_until="domcontentloaded", timeout=45000)
                        again = await find_form(p2, seconds=25)
                        res["popup_again_after_signup"] = again["text"] if again else None
                        res["return_shot"] = await shot(p2, out, f"{args.device}_signup_return.jpg")
                        await c2.close()
            await ctx.close()
        if args.code:
            res["code_check"] = await check_code(browser, origin, plan, args.code, out)
        await browser.close()
    return res


async def check_code(browser, origin: str, plan: dict, code: str, out: Path) -> dict:
    prod = plan.get("product") or {}
    if not (plan.get("platform") or {}).get("shopify") or not prod.get("variant_id"):
        return {"applied": None, "evidence": "Code check runs on Shopify stores only; check it by hand in the cart."}
    ctx = await browser.new_context(locale="en-US", **DEVICES["desktop"])
    page = await ctx.new_page()
    try:
        await page.goto(origin, wait_until="domcontentloaded", timeout=45000)
        await page.evaluate("""async ([b, id]) => fetch(b + '/cart/add.js', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, quantity: 1})})""",
                            [origin, prod["variant_id"]])
        await page.goto(urljoin(origin, f"/discount/{quote(code)}?redirect=/cart"), wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
        cart = await page.evaluate("async (b) => (await fetch(b + '/cart.js')).json()", origin)
        disc = cart.get("total_discount") or 0
        apps = [a.get("title") for a in cart.get("cart_level_discount_applications", [])]
        apps += [a.get("discount_application", {}).get("title") for it in cart.get("items", []) for a in it.get("line_level_discount_allocations", [])]
        name = await shot(page, out, "desktop_code_check.jpg")
        applied = disc > 0 or any(code.lower() == (t or "").lower() for t in apps)
        return {"applied": applied, "shot": name,
                "evidence": f"Code {code} on a cart of {cart.get('original_total_price', 0) / 100:.2f}: discount {disc / 100:.2f}" + (f" ({', '.join(filter(None, apps))})" if apps else "") + "."}
    except Exception as e:  # noqa: BLE001
        return {"applied": None, "evidence": f"Code check failed: {e.__class__.__name__}"}
    finally:
        await ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="Audit folder with walk.json")
    ap.add_argument("--email", help="The tester's own email address to sign up with")
    ap.add_argument("--code", help="A discount code to check in a Shopify cart")
    ap.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    if not args.email and not args.code:
        sys.exit("Give --email (test signup) and/or --code (check a code in the cart).")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = asyncio.run(run(args))
    (Path(args.out) / "signup.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("form_text",)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
