#!/usr/bin/env python3
"""Walk a store like shoppers do before and during a sale, and record what the checklist needs.

Every scenario runs in its own clean browser session (a pop-up app remembers a closed form, so a page seen
after another page can stay silent for that reason alone), on desktop (1440x900) and mobile (390x844):

  home_new      first visit to the homepage: 40 s, scrolling; no layer is closed for the first 12 s so
                stacked layers (cookie banner + pop-up) are caught; then pop-ups are closed and the site
                itself is screenshotted screen by screen; then a category page (does a teaser stay?)
  product_land  first visit straight to a product page, as from an ad click; then the FAQ / help page
  browse_exit   three product pages with pop-ups closed, exit intent on the third
  exit_cart     a product in the cart, homepage, exit intent; then the cart (page or drawer) and the
                checkout, opened and never filled
  return_visit  the home_new visitor comes back with the same cookies and storage
  lang          (desktop) the homepage of one other language version, if the site has one

Exit intent on desktop is the pointer leaving through the top edge; on mobile a quick scroll down and
straight back up, which is what pop-up apps treat as exit on phones. A signup pop-up that shows a button
before its field ("Get 10%", then the email field) gets that button clicked once, so its field can be
measured; links to other pages are never clicked. Nothing is typed or submitted anywhere.

Output: <out>/walk.json and <out>/shots/*.jpg

Usage:
  python walk.py https://store.com --out ./sale-audit/store.com
  python walk.py store.com --out ./a --devices mobile --headed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

HERE = Path(__file__).parent
JS = {n: (HERE / "js" / f"{n}.js").read_text(encoding="utf-8") for n in ("detect", "mobile_check", "close_popup", "page_facts")}

DEVICES = {
    "desktop": dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"),
    "mobile": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                   user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"),
}
HANDS_OFF_S = 12
SCROLL_PLAN = [(4, 10), (8, 25), (12, 40), (16, 55), (20, 70), (25, 85), (30, 100)]
BLOCKING = {"capture_form", "vendor_overlay", "other_overlay", "cookie_banner", "geo_notice"}
SKIP_PRODUCT = re.compile(r"gift[- ]?card|e-?gift|voucher|sample|insurance|shipping[- ]protection|route-|donation", re.I)
# Menu links that are not product listings, in the URL or in the link text.
NOT_CATEGORY = re.compile(r"account|customer|log-?in|sign-?in|register|cart|basket|checkout|wishlist|favou?rite|compare|search|help|faq"
                          r"|support|contact|about|blog|news|journal|stores?\b|locator|delivery|shipping|returns?\b|payment|privacy|terms"
                          r"|policy|legal|cookie|careers?|jobs|gift-?cards?|track-?order|order-?track|loyalty|sitemap|\.(pdf|jpe?g|png)$", re.I)
SALEISH = re.compile(r"sale|deal|black|outlet|clearance|promo|знижк|скидк|розпродаж|распродаж|акці|акци|аутлет|wyprzeda|soldes|rebajas|angebot|offert", re.I)
LANG_ROOT = re.compile(r"^/[a-z]{2}(-[a-z]{2})?/?$", re.I)
CART_PATH = re.compile(r"/(cart|basket|bag|koszyk|kosik|korzina|warenkorb|panier|carrito|carrello|winkelwagen|varukorg)\b|/checkout/cart|cart\.php", re.I)
CART_DEFAULT = {"magento": "/checkout/cart/", "woocommerce": "/cart/", "bigcommerce": "/cart.php"}
ADD_TO_CART_SELECTORS = ["#product-addtocart-button", "button.single_add_to_cart_button", "#form-action-addToCart", "button[name='add']"]
ADD_TO_CART_NAMES = [r"add to (cart|bag|basket)", r"in den warenkorb", r"ajouter au panier", r"añadir", r"buy now",
                     r"(додати )?(в|до) кошик", r"купити", r"(добавить )?в корзину", r"купить", r"(dodaj )?do koszyka",
                     r"aggiungi al carrello", r"in (de )?winkelwagen", r"adicionar ao carrinho", r"lägg i varukorgen"]
CATEGORY_PAGES_MAX = 4
PRODUCT_CHECKS_MAX = 3

# A product page says so in its own markup: schema.org Product (JSON-LD or microdata) or og:type product.
PRODUCT_PAGE_JS = r"""
() => {
  const types = [];
  const add = o => { if (!o || typeof o !== 'object') return; if (Array.isArray(o)) return o.forEach(add);
    for (const t of [].concat(o['@type'] || [])) types.push(String(t)); if (o['@graph']) add(o['@graph']); };
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) { try { add(JSON.parse(s.textContent)); } catch (e) {} }
  const og = (document.querySelector('meta[property="og:type"]') || {}).content || '';
  const h1 = document.querySelector('h1');
  return {product: types.some(t => /^(Product|ProductGroup|IndividualProduct)$/i.test(t)) || /product/i.test(og)
            || !!document.querySelector('[itemtype*="schema.org/Product"]'),
          title: h1 ? h1.innerText.trim().slice(0, 120) : document.title.slice(0, 120)};
}
"""

COOKIE_JS = r"""
() => {
  const sels = ['#onetrust-reject-all-handler', '#CybotCookiebotDialogBodyButtonDecline', '#shopify-pc__banner__btn-decline',
    '#didomi-notice-disagree-button', '[data-testid="uc-deny-all-button"]', '.cc-deny', '.cmplz-deny', '[data-tid="banner-decline"]',
    '.iubenda-cs-reject-btn', '#onetrust-accept-btn-handler', '#shopify-pc__banner__btn-accept', '.cc-allow'];
  for (const s of sels) { const b = document.querySelector(s); if (b && b.offsetParent !== null) { b.click(); return s; } }
  const re = /^(reject( all)?|decline( all)?|only necessary|necessary only|accept( all)?( cookies)?|allow all|i agree|got it|ok)$/i;
  for (const b of document.querySelectorAll('button, a[role=button], [role=button]')) {
    const t = (b.innerText || '').trim();
    if (!re.test(t) || b.offsetParent === null) continue;
    let p = b, ok = false;
    for (let i = 0; i < 8 && p; i++, p = p.parentElement) if (/cookie|consent|privacy|gdpr/i.test((p.id || '') + ' ' + (typeof p.className === 'string' ? p.className : '') + ' ' + (p.innerText || '').slice(0, 400))) { ok = true; break; }
    if (ok) { b.click(); return 'text:' + t; }
  }
  return null;
}
"""

# Pop-up apps built from web components (Claspo) nest a shadow root in every component: fields, buttons and
# text of a layer can sit several shadow roots below its host.
DEEP_JS = r"""
  const roots = () => { const rs = [host];
    for (let i = 0; i < rs.length && rs.length < 400; i++) { const r = rs[i]; if (r.shadowRoot) rs.push(r.shadowRoot);
      for (const n of r.querySelectorAll('*')) if (n.shadowRoot) rs.push(n.shadowRoot); }
    return rs; };
  const deep = sel => roots().flatMap(r => [...r.querySelectorAll(sel)]);
  const deepText = () => roots().map(r => { const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT), out = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) { const p = n.parentElement;
      if (!p || (!/^(STYLE|SCRIPT|NOSCRIPT|TEMPLATE)$/.test(p.tagName) && (!p.checkVisibility || p.checkVisibility({visibilityProperty: true})))) out.push(n.textContent); }
    return out.join(' '); }).join(' ').replace(/\s+/g, ' ').trim();
"""

# Where the contact field of a form sits on a phone: the keyboard takes roughly the bottom 45% of the screen.
FIELD_POS_JS = r"""
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`); if (!host) return null;
""" + DEEP_JS + r"""
  const f = deep('input').find(i => i.type === 'email' || i.type === 'tel' || /email|phone/i.test(i.name + ' ' + i.placeholder));
  if (!f) return null; const r = f.getBoundingClientRect();
  return {field_top: Math.round(r.top), field_bottom: Math.round(r.bottom), viewport_h: innerHeight,
          bottom_share: Math.round(r.bottom / innerHeight * 100) / 100};
}
"""

# Step one of a two-step form: the biggest visible button that does not close the layer, link to another page,
# or buy, add to the cart or apply a code.
OPEN_STEP_JS = r"""
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`); if (!host) return null;
""" + DEEP_JS + r"""
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const label = el => `${el.innerText || el.value || ''} ${el.getAttribute('aria-label') || ''} ${typeof el.className === 'string' ? el.className : ''}`;
  const CLOSE = /close|dismiss|×|✕|no,? thanks|not now|later|закрити|закрыть|ні,? дякую|нет,? спасибо|не зараз|не сейчас|nein danke|non merci|no gracias|nie,? dziękuję/i;
  const BUY = /add to (cart|bag|basket)|buy|check ?out|apply|shop now|shop the|place order|order now|в кошик|до кошика|купити|оформити|замовити|застосувати|в корзину|купить|оформить|заказать|применить|do koszyka|kup teraz|zamów|warenkorb|kaufen|ajouter au panier|acheter|al carrito|comprar/i;
  const leaves = el => el.tagName === 'A' && el.getAttribute('href') && !/^(#|javascript:)/i.test(el.getAttribute('href'));
  const area = el => { const r = el.getBoundingClientRect(); return r.width * r.height; };
  const btn = deep('button, [role=button], input[type=submit], input[type=button], a')
    .filter(b => vis(b) && (b.innerText || b.value || '').trim() && !CLOSE.test(label(b)) && !BUY.test(label(b)) && !leaves(b))
    .sort((a, b) => area(b) - area(a))[0];
  if (!btn) return null;
  btn.click();
  return (btn.innerText || btn.value || '').replace(/\s+/g, ' ').trim().slice(0, 40);
}
"""

CHECKOUT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const txt = el => (el.innerText || el.textContent || el.getAttribute('aria-label') || el.value || '').replace(/\s+/g, ' ').trim();
  const inputs = [...document.querySelectorAll('input, select, textarea')].filter(vis);
  const btns = [...document.querySelectorAll('button, [role=button], a, iframe')].filter(vis);
  const express = btns.map(b => (txt(b) + ' ' + (b.getAttribute('title') || '') + ' ' + (b.getAttribute('src') || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.className || '')).toLowerCase())
    .map(l => (l.match(/shop ?pay|apple ?pay|google ?pay|gpay|paypal|amazon ?pay|meta ?pay|klarna|venmo/) || [])[0]).filter(Boolean);
  const checkboxes = inputs.filter(i => i.type === 'checkbox').map(i => {
    const lab = i.closest('label') || (i.id && document.querySelector(`label[for="${i.id}"]`));
    return {label: lab ? txt(lab).slice(0, 160) : (i.name || ''), checked: i.checked};
  });
  return {
    url: location.href, title: document.title,
    text: (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 5000),
    fields: inputs.filter(i => !['hidden', 'checkbox', 'radio', 'submit'].includes(i.type)).map(i => ({name: i.name || i.id, type: i.type, autocomplete: i.getAttribute('autocomplete')})).slice(0, 30),
    checkboxes, express_buttons: [...new Set(express)],
    login_prompt: /log in|sign in|already have an account/i.test(document.body.innerText || ''),
  };
}
"""

LCP_JS = r"""
() => new Promise(res => { let v = null;
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) v = e.startTime; }).observe({type: 'largest-contentful-paint', buffered: true}); } catch (e) {}
  setTimeout(() => res(v == null ? null : Math.round(v)), 300); })
"""

HREFLANG_JS = r"""() => [...document.querySelectorAll('link[rel=alternate][hreflang]')].map(l => ({lang: l.hreflang, href: l.href}))"""

TIMER_JS = r"""() => [...document.querySelectorAll('body *')].filter(el => el.children.length < 14 && el.offsetParent !== null
  && /\b\d{1,2}\s*[:hdд]\s*\d{1,2}\s*[:mм]\s*\d{1,2}/i.test((el.innerText||'').slice(0,80)) && (el.innerText||'').length < 140)
  .slice(0, 8).map(el => (el.innerText||'').replace(/\s+/g,' ').trim())"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Device:
    def __init__(self, browser, device: str, base: str, out: Path, plan: dict):
        self.browser, self.device, self.base, self.out, self.plan = browser, device, base, out, plan
        self.events: list[dict] = []
        self.shots: list[dict] = []
        self.pages: dict = {}
        self.errors: list[str] = []
        self.form_layers: set[str] = set()  # pa_ids of two-step forms whose first view shows no field

    # --- helpers --------------------------------------------------------------------------
    async def context(self, storage=None):
        ctx = await self.browser.new_context(locale="en-US", storage_state=storage, **DEVICES[self.device])
        return ctx, await ctx.new_page()

    async def shot(self, page, scenario: str, label: str, full: bool = False):
        name = f"{self.device}_{scenario}_{len(self.shots) + 1:02d}_{label}.jpg"
        try:
            await page.screenshot(path=str(self.out / "shots" / name), type="jpeg", quality=62, full_page=full, timeout=20000)
        except Exception as e:  # noqa: BLE001 - a failed screenshot must not stop the walk
            return None
        self.shots.append({"file": name, "device": self.device, "scenario": scenario, "label": label})
        return name

    async def goto(self, page, url: str, scenario: str, settle_ms: int = 2500) -> bool:
        try:
            r = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = r.status if r else None
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"{scenario}: {url} did not load ({e.__class__.__name__})")
            return False
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(settle_ms)
        title = (await page.title())[:120]
        if re.search(r"just a moment|attention required|access denied|captcha|are you human", title, re.I):
            self.errors.append(f"{scenario}: bot check on {url} ({title})")
        if status and status >= 400:
            self.errors.append(f"{scenario}: HTTP {status} on {url}")
        return True

    async def exit_intent(self, page, scenario: str):
        if self.device == "desktop":
            await page.mouse.move(700, 400)
            await page.mouse.move(700, 2, steps=8)
            await page.evaluate("""() => { const o = {bubbles: false, cancelable: true, clientX: 700, clientY: -5, relatedTarget: null};
                document.body.dispatchEvent(new MouseEvent('mouseleave', o));
                document.documentElement.dispatchEvent(new MouseEvent('mouseleave', o));
                document.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, clientX: 700, clientY: -5, relatedTarget: null})); }""")
        else:
            await page.evaluate("""async () => { const h = document.scrollingElement.scrollHeight - innerHeight;
                const d = Math.round(Math.max(120, Math.min(600, h * 0.08))); window.scrollTo(0, d);
                await new Promise(r => setTimeout(r, 700)); window.scrollTo(0, 0); }""")
        self.events.append({"scenario": scenario, "device": self.device, "event": "exit_intent_simulated"})

    async def answer_cookies(self, page):
        try:
            return await page.evaluate(COOKIE_JS)
        except Exception:  # noqa: BLE001
            return None

    async def close_layer(self, page, o):
        try:
            res = await page.evaluate(JS["close_popup"], o["pa_id"])
        except Exception:  # noqa: BLE001
            res = None
        if not res:
            await page.keyboard.press("Escape")

    async def open_next_step(self, page, o) -> dict | None:
        """A signup app's pop-up with no field may be step one of a form ("Get 10%" first, the email field
        after it). Click its main button once, never a link that leaves the page, and read the next view."""
        url = page.url
        try:
            clicked = await page.evaluate(OPEN_STEP_JS, o["pa_id"])
        except Exception:  # noqa: BLE001
            return None
        if not clicked:
            return None
        await page.wait_for_timeout(1500)
        if page.url != url:
            try:
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
            except Exception:  # noqa: BLE001
                pass
            return None
        try:
            snap = await page.evaluate(JS["detect"])
        except Exception:  # noqa: BLE001
            return None
        same = [x for x in snap["overlays"] if x["pa_id"] == o["pa_id"]]
        form = next((x for x in same + snap["overlays"] if x["kind"] == "capture_form" and (x["has_email"] or x["has_tel"])), None)
        return {"clicked": clicked, "layer": form or (same[0] if same else None)}

    async def watch(self, page, scenario: str, seconds: float, scroll: bool = True, exit_at: float | None = None,
                    hands_off: float = HANDS_OFF_S, close_after: bool = True):
        """Log every overlay that appears; after `hands_off` s answer cookies and close pop-ups like a visitor."""
        t0 = time.monotonic()
        seen, plan, acted, overlaps, opened = {}, list(SCROLL_PLAN) if scroll else [], False, set(), set()
        exits = [exit_at, exit_at + 3, exit_at + 6] if exit_at is not None else []
        while (t := time.monotonic() - t0) < seconds:
            try:
                if plan and t >= plan[0][0]:
                    _, pct = plan.pop(0)
                    await page.evaluate(f"window.scrollTo({{top: (document.scrollingElement.scrollHeight - innerHeight) * {pct / 100}}})")
                if exits and t >= exits[0]:
                    exits.pop(0)
                    await self.exit_intent(page, scenario)
                snap = await page.evaluate(JS["detect"])
            except Exception:  # noqa: BLE001 - navigation in progress
                await asyncio.sleep(0.5)
                continue
            current = {o["key"]: o for o in snap["overlays"]}
            for key, o in current.items():
                if key in seen or o["pa_id"] in opened:  # the next view of a form opened below is not a new form
                    continue
                seen[key] = o
                await asyncio.sleep(0.8)  # entrance animation
                ev = {"scenario": scenario, "device": self.device, "event": "appeared", "t_s": round(t, 1),
                      "url": page.url, "scroll_pct": snap.get("scroll_pct"), "during_hands_off": t < hands_off,
                      "after_exit_attempt": exit_at is not None and t >= exit_at,
                      **{k: v for k, v in o.items() if k not in ("key",)}}
                ev["screenshot"] = await self.shot(page, scenario, o["kind"])
                measured = o
                if o["kind"] == "vendor_overlay" and o.get("on_top") and scenario not in ("cart", "checkout"):
                    step = await self.open_next_step(page, o)
                    if step and step["layer"]:
                        n = step["layer"]
                        opened.update({o["pa_id"], n["pa_id"]})
                        ev.update(opened_with=step["clicked"], next_step_text=n["text"])
                        if n["kind"] == "capture_form":
                            self.form_layers.update({o["pa_id"], n["pa_id"]})
                            ev.update(kind="capture_form", two_step=True, has_email=n["has_email"], has_tel=n["has_tel"], inputs=n["inputs"])
                            ev["next_step_screenshot"] = await self.shot(page, scenario, "capture_form_step2")
                            measured = n
                if self.device == "mobile" and ev["kind"] == "capture_form":
                    try:
                        ev["mobile_fit"] = await page.evaluate(JS["mobile_check"], measured["pa_id"])
                        ev["field_position"] = await page.evaluate(FIELD_POS_JS, measured["pa_id"])
                    except Exception:  # noqa: BLE001
                        pass
                self.events.append(ev)
                if acted and close_after and o["kind"] in ("capture_form", "vendor_overlay", "other_overlay", "geo_notice"):
                    await asyncio.sleep(1)
                    await self.close_layer(page, o)
            blocking = [o for o in current.values() if o["kind"] in BLOCKING]
            if len(blocking) >= 2:
                k = tuple(sorted(o["key"] for o in blocking))
                if k not in overlaps:
                    overlaps.add(k)
                    self.events.append({"scenario": scenario, "device": self.device, "event": "overlap", "t_s": round(t, 1),
                                        "layers": [{"kind": "capture_form" if o["pa_id"] in self.form_layers else o["kind"],
                                                    "vendor": o["vendor"], "text": o["text"][:80]} for o in blocking],
                                        "screenshot": await self.shot(page, scenario, "overlap")})
            if not acted and t >= hands_off:
                acted = True
                await self.answer_cookies(page)
                if close_after:
                    for o in current.values():
                        if o["kind"] in ("capture_form", "vendor_overlay", "other_overlay", "geo_notice"):
                            await self.close_layer(page, o)
            await asyncio.sleep(0.5)
        return list(seen.values())

    async def clear(self, page):
        if not await self.answer_cookies(page):
            # consent tools that render in shadow DOM: role locators pierce it
            for name in (r"^(decline|reject all|reject|necessary only|only necessary|deny)$", r"^(accept all|accept|allow all|i agree|got it|ok)$"):
                try:
                    loc = page.get_by_role("button", name=re.compile(name, re.I))
                    if await loc.count() and await loc.first.is_visible():
                        await loc.first.click(timeout=3000)
                        await page.wait_for_timeout(600)
                        break
                except Exception:  # noqa: BLE001
                    continue
        try:
            snap = await page.evaluate(JS["detect"])
            for o in snap["overlays"]:
                if o["kind"] in ("capture_form", "vendor_overlay", "other_overlay", "geo_notice", "cookie_banner"):
                    await self.close_layer(page, o)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(700)

    async def facts(self, page) -> dict:
        try:
            f = await page.evaluate(JS["page_facts"])
        except Exception as e:  # noqa: BLE001
            return {"error": f"{e.__class__.__name__}"}
        try:
            a = await page.evaluate(TIMER_JS)
            await page.wait_for_timeout(2500)
            b = await page.evaluate(TIMER_JS)
            f["live_timers"] = [y for x, y in zip(a, b) if x != y][:4]
        except Exception:  # noqa: BLE001
            f["live_timers"] = []
        return f

    async def screens(self, page, scenario: str, max_n: int):
        h = page.viewport_size["height"]
        total = await page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        n = min(max_n, max(1, -(-total // h)))
        step = max(h, (total - h) // max(1, n - 1)) if n > 1 else h
        for i in range(n):
            y = min(i * step, max(0, total - h))
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(1100)
            await self.shot(page, scenario, f"screen{i + 1}")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        await self.shot(page, scenario, "footer")
        await page.evaluate("window.scrollTo(0, 0)")

    async def add_to_cart(self, page) -> str:
        prod = self.plan.get("product")
        if prod and prod.get("variant_id"):
            try:
                st = await page.evaluate("""async ([base, id]) => (await fetch(base + '/cart/add.js', {method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}, body: JSON.stringify({id, quantity: 1})})).status""",
                                         [self.base, prod["variant_id"]])
                if st == 200:
                    return "cart_api"
            except Exception:  # noqa: BLE001
                pass
        if prod and prod.get("url") and await self.goto(page, prod["url"], "exit_cart"):
            await self.clear(page)
            buttons = [page.locator(s).filter(visible=True) for s in ADD_TO_CART_SELECTORS]
            buttons += [page.get_by_role("button", name=re.compile(pat, re.I)) for pat in ADD_TO_CART_NAMES]
            for btn in buttons:
                try:
                    if await btn.count():
                        await btn.first.click(timeout=6000)
                        await page.wait_for_timeout(2500)
                        return "button"
                except Exception:  # noqa: BLE001
                    continue
        return "failed"

    # --- scenarios ------------------------------------------------------------------------
    async def run(self):
        for name in ("home_new", "product_land", "browse_exit", "exit_cart", "lang"):
            if name == "lang" and self.device != "desktop":
                continue
            try:
                log(f"{self.device}: {name}")
                await getattr(self, name)()
            except Exception as e:  # noqa: BLE001 - one scenario failing leaves the others
                self.errors.append(f"{name}: {e.__class__.__name__}: {str(e)[:200]}")

    async def home_new(self):
        ctx, page = await self.context()
        try:
            if not await self.goto(page, self.base, "home_new", settle_ms=500):
                return
            await self.shot(page, "home_new", "first_view")
            await self.watch(page, "home_new", 40)
            await page.evaluate("window.scrollTo(0, 0)")
            await self.clear(page)
            lcp = await page.evaluate(LCP_JS)
            await self.shot(page, "home", "above_fold")
            f = await self.facts(page)
            f["lcp_ms"] = lcp
            self.pages["home"] = f
            await self.screens(page, "home", 8 if self.device == "desktop" else 10)
            # teaser after the close, on the next page
            if self.plan.get("category"):
                if await self.goto(page, self.plan["category"], "home_new_next"):
                    await self.watch(page, "home_new_next", 8, scroll=False, hands_off=0, close_after=False)
                    await self.shot(page, "category", "top")
                    await page.evaluate("window.scrollTo(0, innerHeight)")
                    await page.wait_for_timeout(1200)
                    await self.shot(page, "category", "screen2")
                    await self.clear(page)
                    self.pages["category"] = await self.facts(page)
            storage = await ctx.storage_state()
        finally:
            await ctx.close()
        # the same visitor comes back
        ctx, page = await self.context(storage=storage)
        try:
            if await self.goto(page, self.base, "return_visit", settle_ms=500):
                await self.watch(page, "return_visit", 25, scroll=True, close_after=False)
                await self.shot(page, "return_visit", "end")
        finally:
            await ctx.close()

    async def product_land(self):
        prod = self.plan.get("product")
        if not prod:
            self.errors.append("product_land: no product page found")
            return
        ctx, page = await self.context()
        try:
            if not await self.goto(page, prod["url"], "product_land", settle_ms=500):
                return
            await self.watch(page, "product_land", 30)
            await page.evaluate("window.scrollTo(0, 0)")
            await self.clear(page)
            await self.shot(page, "product", "top")
            await page.evaluate("window.scrollTo(0, innerHeight * 0.9)")
            await page.wait_for_timeout(1100)
            await self.shot(page, "product", "screen2")
            await page.evaluate("window.scrollTo(0, 0)")
            self.pages["product"] = await self.facts(page)
            if self.plan.get("faq") and await self.goto(page, self.plan["faq"], "faq"):
                await self.clear(page)
                await self.shot(page, "faq", "top")
                await page.evaluate("window.scrollTo(0, innerHeight * 0.9)")
                await page.wait_for_timeout(1000)
                await self.shot(page, "faq", "screen2")
                self.pages["faq"] = await self.facts(page)
        finally:
            await ctx.close()

    async def browse_exit(self):
        urls = self.plan.get("browse") or []
        if len(urls) < 2:
            self.errors.append("browse_exit: fewer than two product pages found")
            return
        ctx, page = await self.context()
        try:
            for i, u in enumerate(urls[:3]):
                if not await self.goto(page, u, "browse_exit"):
                    continue
                if i < len(urls[:3]) - 1:
                    await self.watch(page, "browse_exit_view", 8, scroll=True, hands_off=0)
                    await self.clear(page)
                else:
                    await self.clear(page)
                    await self.watch(page, "browse_exit", 16, scroll=False, exit_at=3, hands_off=99, close_after=False)
        finally:
            await ctx.close()

    async def exit_cart(self):
        ctx, page = await self.context()
        try:
            if not await self.goto(page, self.base, "exit_cart", settle_ms=1500):
                return
            how = await self.add_to_cart(page)
            self.pages["add_to_cart"] = how
            if how == "failed":
                self.errors.append("exit_cart: could not add a product to the cart")
            await self.goto(page, self.base, "exit_cart", settle_ms=1500)
            await self.clear(page)
            await self.watch(page, "exit_cart", 16, scroll=False, exit_at=3, hands_off=99, close_after=False)
            await self.clear(page)
            # the cart: a page, or a drawer when /cart redirects
            if await self.goto(page, self.plan.get("cart") or urljoin(self.base, "/cart"), "cart"):
                kind = "page"
                if not CART_PATH.search(urlparse(page.url).path):
                    kind = "drawer"
                    for sel in ['a[href$="/cart"]', 'a[href*="/cart"]', 'button[aria-label*="cart" i]', 'button[aria-label*="bag" i]', '[class*="cart-icon"]']:
                        loc = page.locator(sel).filter(visible=True)
                        try:
                            if await loc.count():
                                await loc.first.click(timeout=5000)
                                await page.wait_for_timeout(2500)
                                break
                        except Exception:  # noqa: BLE001
                            continue
                await self.watch(page, "cart", 10, scroll=False, hands_off=0, close_after=False)
                await self.shot(page, "cart", "top")
                await page.mouse.wheel(0, 600)
                await page.wait_for_timeout(900)
                await self.shot(page, "cart", "screen2")
                f = await self.facts(page)
                f["cart_kind"] = kind
                f["checkout_view"] = await page.evaluate(CHECKOUT_JS)
                self.pages["cart"] = f
            if await self.goto(page, urljoin(self.base, "/checkout"), "checkout", settle_ms=6000):
                await self.watch(page, "checkout", 10, scroll=False, hands_off=0, close_after=False)
                await self.shot(page, "checkout", "top")
                await self.shot(page, "checkout", "full", full=True)
                self.pages["checkout"] = await page.evaluate(CHECKOUT_JS)
        finally:
            await ctx.close()

    async def lang(self):
        alt = self.plan.get("other_language")
        if not alt:
            return
        ctx, page = await self.context()
        try:
            if await self.goto(page, alt["href"], "lang", settle_ms=500):
                await self.watch(page, "lang", 25)
                await self.shot(page, "lang", "end")
        finally:
            await ctx.close()


async def discover(browser, base: str) -> dict:
    """Find, without counting as a visit: the real origin, platform, a buyable product, two more products,
    a category, the cart, the FAQ page and one other language version. Products are found by their cards
    (picture and price) and confirmed by the product page's own markup, so any URL scheme works."""
    ctx = await browser.new_context(locale="en-US", **DEVICES["desktop"])
    page = await ctx.new_page()
    plan: dict = {"errors": []}
    try:
        await page.goto(base, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(3000)
        origin = f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"
        plan["origin"] = origin
        f = await page.evaluate(JS["page_facts"])
        plan["platform"] = f.get("platform")
        host = urlparse(origin).netloc.replace("www.", "")
        same = lambda u: urlparse(urljoin(origin, u)).netloc.replace("www.", "") == host  # noqa: E731
        base_dom = ".".join(host.split(".")[-3:] if re.search(r"\.(co|com|org|net)\.[a-z]{2}$", host) else host.split(".")[-2:])
        own = lambda u: urlparse(urljoin(origin, u)).netloc.endswith(base_dom)  # noqa: E731 - help.store.com counts
        # menus hide their links until hovered, so read every header/nav link, visible or not
        hidden = await page.evaluate(r"""() => [...document.querySelectorAll('header a[href], nav a[href], [class*="menu"] a[href]')]
            .map(a => ({h: a.getAttribute('href'), t: (a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60)}))""")
        links = [l for k in ("header", "footer") for l in ((f.get(k) or {}).get("links") or [])] + hidden
        links += [{"h": c.get("href"), "t": c.get("text", "")} for c in f.get("category_tiles") or []]
        hrefs = [urljoin(origin, l["h"]) for l in links if l.get("h") and same(l["h"])]
        platform = plan["platform"] or {}
        alts = await page.evaluate(HREFLANG_JS)  # the homepage's language versions, read before leaving it
        cart = [h for h in hrefs if CART_PATH.search(urlparse(h).path)]
        plan["cart"] = cart[0] if cart else urljoin(origin, next((c for k, c in CART_DEFAULT.items() if platform.get(k)), "/cart"))
        # category: URL patterns first, then any menu link that may list products, sale-like ones first
        by_url = [h for pat in [r"/collections/(?!all\b)[^/?#]+$", r"/collections/", r"/(category|categories|shop|c)/", r"sale|deal|black"]
                  for h in hrefs if re.search(pat, h, re.I)]
        if platform.get("shopify"):
            by_url.append(urljoin(origin, "/collections/all"))
        menu = [(urljoin(origin, l["h"]), l.get("t") or "") for l in (f.get("header") or {}).get("links", []) + hidden if l.get("h") and same(l["h"])]
        menu = [(h, t) for h, t in menu if 1 <= len([x for x in urlparse(h).path.split("/") if x]) <= 3
                and not LANG_ROOT.match(urlparse(h).path) and not NOT_CATEGORY.search(urlparse(h).path + " " + t)]
        menu.sort(key=lambda x: not SALEISH.search(x[0] + " " + x[1]))
        candidates = list(dict.fromkeys(h.split("#")[0] for h in by_url + [h for h, _ in menu]))
        # the store's general FAQ / help centre: a link named so wins over any page with "faq" in its path
        faq = [(urljoin(origin, l["h"]), (l.get("t") or "").strip()) for l in links
               if l.get("h") and own(l["h"]) and re.search(r"faq|help|support|frequently", l["h"] + " " + (l.get("t") or ""), re.I)]
        named = re.compile(r"^(faqs?|help( cent(re|er))?|support|customer (service|care)|frequently asked questions)$", re.I)
        faq.sort(key=lambda x: (not named.match(x[1]), len(urlparse(x[0]).path)))
        plan["faq"] = faq[0][0] if faq else None
        tiles = [urljoin(origin, t["href"]) for t in f.get("product_tiles") or [] if t.get("href")]
        best = None
        for url in candidates[:CATEGORY_PAGES_MAX]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
                cf = await page.evaluate(JS["page_facts"])
            except Exception:  # noqa: BLE001
                continue
            found = [urljoin(origin, t["href"]) for t in cf.get("product_tiles") or [] if t.get("href")]
            if best is None or len(found) > len(best[1]):
                best = (url, found)
            if len(found) >= 4:
                break
        if best and best[1]:
            plan["category"], tiles = best[0], best[1] + tiles
        elif by_url:  # a category page by its URL even when its products did not load; a bare menu link is no category
            plan["category"] = by_url[0]
        tiles = [t for i, t in enumerate(tiles) if same(t) and not SKIP_PRODUCT.search(t) and t not in tiles[:i]]
        if not platform.get("shopify"):
            for url in tiles[:PRODUCT_CHECKS_MAX]:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                    info = await page.evaluate(PRODUCT_PAGE_JS)
                except Exception:  # noqa: BLE001
                    continue
                if info.get("product"):
                    plan["product"] = {"url": url, "title": info.get("title")}
                    break
        if platform.get("shopify"):
            handles = [m.group(1) for t in tiles if (m := re.search(r"/products/([^/?#]+)", t))]
            try:
                data = await page.evaluate("async (b) => { const r = await fetch(b + '/products.json?limit=50'); return r.ok ? await r.json() : null; }", origin)
                handles += [p["handle"] for p in (data or {}).get("products", []) if not SKIP_PRODUCT.search(p["handle"] + " " + (p.get("product_type") or ""))]
            except Exception:  # noqa: BLE001
                pass
            for h in dict.fromkeys(handles):
                try:
                    p = await page.evaluate("async ([b, h]) => { const r = await fetch(b + '/products/' + h + '.js'); return r.ok ? await r.json() : null; }", [origin, h])
                except Exception:  # noqa: BLE001
                    continue
                v = next((v for v in (p or {}).get("variants", []) if v.get("available") and (v.get("price") or 0) > 0), None)
                if v:
                    plan["product"] = {"url": urljoin(origin, f"/products/{h}"), "variant_id": v["id"], "title": p.get("title"),
                                       "discounted": bool(v.get("compare_at_price") and v["compare_at_price"] > v["price"])}
                    break
            tiles = tiles or [urljoin(origin, f"/products/{h}") for h in list(dict.fromkeys(handles))[:4]]
        if not plan.get("product") and tiles:
            plan["product"] = {"url": tiles[0]}
        others = [t for t in tiles if not plan.get("product") or t != plan["product"]["url"]]
        plan["browse"] = ([plan["product"]["url"]] if plan.get("product") else []) + others[:2]
        own = (f.get("lang") or "en")[:2].lower()
        brand = host.split(".")[-2] if host.count(".") >= 1 else host  # allbirds.com -> allbirds; store.co.uk keeps 'co' risk low
        brand = host.split(".")[0] if brand in ("co", "com") else brand
        other = [a for a in alts if a["lang"] != "x-default" and a["lang"][:2].lower() != own and a["href"].rstrip("/") != origin
                 and brand in urlparse(a["href"]).netloc]  # the store's own versions, not a distributor's site
        plan["languages"] = sorted({a["lang"] for a in alts})
        plan["other_language"] = other[0] if other else None
    except Exception as e:  # noqa: BLE001
        plan["errors"].append(f"discover: {e.__class__.__name__}: {str(e)[:200]}")
    finally:
        await ctx.close()
    return plan


async def main_async(args) -> int:
    base = args.url if args.url.startswith("http") else f"https://{args.url}"
    out = Path(args.out)
    (out / "shots").mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    async with async_playwright() as p:
        b0 = await p.chromium.launch(headless=not args.headed, args=["--disable-blink-features=AutomationControlled"])
        log(f"discover {base}")
        plan = await discover(b0, base)
        await b0.close()
        if not plan.get("origin"):
            print("WALK FAILED: the homepage did not load: " + "; ".join(plan.get("errors", [])), file=sys.stderr)
            return 2
        log(f"plan: product={(plan.get('product') or {}).get('url')} category={plan.get('category')} cart={plan.get('cart')} faq={plan.get('faq')} lang={plan.get('other_language')}")
        devs = []
        browsers = []
        for d in args.devices.split(","):
            br = await p.chromium.launch(headless=not args.headed, args=["--disable-blink-features=AutomationControlled"])
            browsers.append(br)
            devs.append(Device(br, d, plan["origin"], out, plan))
        await asyncio.gather(*(d.run() for d in devs))
        for br in browsers:
            await br.close()
    walk = {
        "site": plan["origin"], "requested": base, "started_utc": started.strftime("%Y-%m-%d %H:%M"),
        "minutes": round((datetime.now(timezone.utc) - started).total_seconds() / 60, 1),
        "plan": plan,
        "devices": {d.device: {"pages": d.pages, "events": d.events, "shots": d.shots, "errors": d.errors} for d in devs},
    }
    (out / "walk.json").write_text(json.dumps(walk, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(d.shots) for d in devs)
    log(f"done: {n} screenshots, {sum(len(d.events) for d in devs)} events -> {out / 'walk.json'}")
    for d in devs:
        for e in d.errors:
            log(f"  {d.device} warning: {e}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url", help="Store URL or domain")
    ap.add_argument("--out", required=True, help="Folder for walk.json and shots/")
    ap.add_argument("--devices", default="desktop,mobile", help="desktop,mobile (default both)")
    ap.add_argument("--headed", action="store_true", help="Show the browsers")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
