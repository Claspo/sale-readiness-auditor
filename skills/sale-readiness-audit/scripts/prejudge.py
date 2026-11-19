#!/usr/bin/env python3
"""Turn walk.json (and signup.json, if the test signup ran) into draft.json: one entry per checklist item.

Items marked "auto" in checklist.json get a status and evidence computed here from what the walk measured.
Items marked "visual" get no status: they list the screenshots and the page facts to look at, and the
agent running the audit judges them by viewing those screenshots. Items marked "manual" wait for the
tester (the welcome email).

Usage:
  python prejudge.py --out ./sale-audit/store.com
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
CHECKLIST = json.loads((HERE.parent / "checklist.json").read_text(encoding="utf-8"))

PCT = re.compile(r"(\d{1,2})\s?%")
USD = re.compile(r"[$€£]\s?(\d{1,4})\s?(off|discount)", re.I)
FREE_SHIP = re.compile(r"free (shipping|delivery)", re.I)
GIFT = re.compile(r"free gift|gift with|mystery gift", re.I)
EARLY = re.compile(r"early access|first access|vip access|be the first", re.I)
SALE_WORDS = re.compile(r"black friday|cyber monday|bfcm|black week|cyber week|holiday sale|early access|sale", re.I)
GAME = re.compile(r"spin|wheel|scratch|mystery|try your luck|win", re.I)
QUIZ = re.compile(r"\?|which|what (are|is) your|tell us|choose|select your|are you", re.I)
TIMER = re.compile(r"\b\d{1,2}\s*[:hd]\s*\d{1,2}\s*[:m]\s*\d{1,2}", re.I)
NOT_A_POPUP = re.compile(r"\bcart \(\d+\)|subtotal|your (cart|bag) is empty|proceed to checkout|size (guide|chart)", re.I)
GEOISH = re.compile(r"shipping to\?|ship to|choose your (country|region)|select your (country|region)|country/region|you('re| are) (in|visiting|shopping from)", re.I)
ENGLISH = re.compile(r"\b(the|your|get|off|sign up|subscribe|email|first order|and|you|discount|join)\b", re.I)


def sig(text: str) -> str:
    return re.sub(r"[^a-z0-9% ]", "", (text or "").lower())[:70].strip()


def offer(text: str) -> dict:
    t = text or ""
    kinds = []
    pcts = [int(x) for x in PCT.findall(t) if 0 < int(x) < 90]
    if pcts:
        kinds.append("% off")
    if USD.search(t):
        kinds.append("$ off")
    if FREE_SHIP.search(t):
        kinds.append("free shipping")
    if GIFT.search(t):
        kinds.append("gift")
    if EARLY.search(t):
        kinds.append("early access")
    return {"kinds": kinds or ["no incentive stated"], "max_pct": max(pcts) if pcts else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="Audit folder with walk.json")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = Path(args.out)
    walk = json.loads((out / "walk.json").read_text(encoding="utf-8"))
    signup = json.loads((out / "signup.json").read_text(encoding="utf-8")) if (out / "signup.json").exists() else None
    devs = walk["devices"]
    D = list(devs)

    def events(dev, scen, kind=None, after_exit=None):
        r = [e for e in devs.get(dev, {}).get("events", []) if e.get("event") == "appeared" and e["scenario"] == scen]
        if kind:
            r = [e for e in r if e["kind"] == kind]
        if after_exit is not None:
            r = [e for e in r if e.get("after_exit_attempt") == after_exit]
        return r

    def forms(dev, scen, after_exit=None):
        return events(dev, scen, "capture_form", after_exit)

    def ev_ref(e):
        return f"{e['device']} {e['scenario']} at {e.get('t_s')} s: \"{(e.get('text') or '')[:110]}\""

    def shots_of(es):
        return [e["screenshot"] for e in es if e.get("screenshot")]

    def page(dev, name):
        return devs.get(dev, {}).get("pages", {}).get(name) or {}

    reached = {d: set(devs[d].get("pages", {})) for d in D}
    geo_seen = [e for d in D for e in devs[d].get("events", []) if e.get("event") == "appeared" and (e["kind"] == "geo_notice" or GEOISH.search(e.get("text") or ""))]
    GEO_NOTE = (f" The store showed a country picker (\"{geo_seen[0]['text'][:60]}\"): it reacts to this machine's location, so a form shown only to visitors from other countries would not appear here."
                if geo_seen else "")
    res: dict[str, dict] = {}

    def put(i, status, evidence, shots=None, **extra):
        res[i] = {"status": status, "evidence": evidence, "screenshots": [s for s in (shots or []) if s][:4], **extra}

    all_forms = [e for d in D for e in devs[d].get("events", []) if e.get("event") == "appeared" and e["kind"] == "capture_form"]
    home_forms = {d: forms(d, "home_new") for d in D}

    # E1 / E2: per device presence
    for iid, scen in (("E1", "home_new"), ("E2", "product_land")):
        per = {d: forms(d, scen) for d in D}
        have = [d for d in D if per[d]]
        ran = [d for d in D if any(e.get("scenario") == scen for e in devs[d].get("events", [])) or (scen == "home_new" and "home" in reached[d]) or (scen == "product_land" and "product" in reached[d])]
        if not ran:
            put(iid, "cannot_verify", f"The {scen} scenario did not run: {'; '.join(e for d in D for e in devs[d]['errors'] if scen in e) or 'page not reached'}.")
        elif len(have) == len(D):
            put(iid, "done", "; ".join(ev_ref(per[d][0]) for d in have), shots_of([per[d][0] for d in have]))
        elif have:
            put(iid, "partial", f"Only on {', '.join(have)}: " + "; ".join(ev_ref(per[d][0]) for d in have) + f". Nothing with a contact field on {', '.join(set(D) - set(have))}.", shots_of([per[d][0] for d in have]))
        else:
            put(iid, "missing", f"No pop-up with an email or phone field appeared in {scen} on {', '.join(D)}." + GEO_NOTE,
                [s["file"] for d in D for s in devs[d]["shots"] if s["scenario"] in (scen, "home") and s["label"] in ("first_view", "above_fold", "top")][:2])

    # E3 / E4: after an exit attempt
    for iid, scen in (("E3", "browse_exit"), ("E4", "exit_cart")):
        per = {d: forms(d, scen, after_exit=True) for d in D}
        tried = [d for d in D if any(e.get("event") == "exit_intent_simulated" and e["scenario"] == scen for e in devs[d]["events"])]
        have = [d for d in tried if per[d]]
        if not tried:
            put(iid, "cannot_verify", f"No exit attempt was made in {scen}: " + ("; ".join(e for d in D for e in devs[d]["errors"] if scen in e) or "scenario did not run") + ".")
        elif have:
            st = "done" if len(have) == len(tried) else "partial"
            put(iid, st, "; ".join(ev_ref(per[d][0]) for d in have) + ("" if st == "done" else f". Nothing after exit on {', '.join(set(tried) - set(have))}."), shots_of([per[d][0] for d in have]))
        else:
            put(iid, "missing", f"Exit intent tried three times on {', '.join(tried)} ({scen}); no form appeared." + GEO_NOTE)

    # E5: exit form vs welcome form
    welcome = {sig(e["text"]) for e in all_forms if e["scenario"] in ("home_new", "product_land")}
    exitf = [e for e in all_forms if e["scenario"] in ("browse_exit", "exit_cart") and e.get("after_exit_attempt")]
    if not exitf:
        put("E5", "not_applicable", "No form appeared on exit.")
    elif any(sig(e["text"]) not in welcome for e in exitf):
        e = next(e for e in exitf if sig(e["text"]) not in welcome)
        put("E5", "done", "Exit form differs from the welcome form: " + ev_ref(e), shots_of([e]))
    else:
        put("E5", "partial", "The exit form is the welcome form again: " + ev_ref(exitf[0]), shots_of([exitf[0]]))

    # F1: distinct forms
    distinct = {sig(e["text"]) for e in all_forms if sig(e["text"])}
    if not all_forms:
        put("F1", "not_applicable", "No signup form seen.")
    elif len(distinct) > 1:
        put("F1", "done", f"{len(distinct)} different signup forms across scenarios: " + " | ".join(sorted(distinct))[:400])
    else:
        put("F1", "missing", f"One form everywhere it appeared ({', '.join(sorted({e['scenario'] for e in all_forms}))}): \"{all_forms[0]['text'][:110]}\".", shots_of(all_forms[:1]))

    # F2: returning visitor
    if not any(home_forms.values()):
        put("F2", "not_applicable", "No welcome form on the first visit.")
    else:
        parts, worst = [], "done"
        for d in D:
            if not home_forms[d]:
                continue
            ret = forms(d, "return_visit")
            first = {sig(e["text"]) for e in home_forms[d]}
            if not ret:
                parts.append(f"{d}: no form on the return visit")
            elif any(sig(e["text"]) in first for e in ret):
                parts.append(f"{d}: the same form again ({ret[0]['text'][:80]})")
                worst = "partial"
            else:
                parts.append(f"{d}: a different form ({ret[0]['text'][:80]})")
        put("F2", worst, "; ".join(parts), shots_of([e for d in D for e in forms(d, "return_visit")]))

    # F3: subscribers
    if not signup or not signup.get("submitted"):
        put("F3", "cannot_verify", "The test signup was not run (signup_test.py), so a subscriber's visit was not seen.")
    elif signup.get("popup_again_after_signup"):
        put("F3", "missing", f"After the test signup the next visit showed a signup form again: \"{signup['popup_again_after_signup'][:110]}\".", [signup.get("return_shot")])
    else:
        put("F3", "done", "After the test signup the next homepage visit (25 s) showed no signup form.", [signup.get("return_shot")])

    # F4: discount pop-up in cart / checkout
    cc = [e for d in D for e in devs[d]["events"] if e.get("event") == "appeared" and e["scenario"] in ("cart", "checkout") and e["kind"] == "capture_form"]
    if not any("cart" in reached[d] or "checkout" in reached[d] for d in D):
        put("F4", "cannot_verify", "Neither the cart nor the checkout was reached.")
    elif cc:
        put("F4", "missing", "A signup form opened on the " + "; ".join(ev_ref(e) for e in cc[:2]), shots_of(cc))
    else:
        put("F4", "done", "No signup pop-up opened in the cart or at checkout (10 s each, both devices).")

    # G1: teaser after close
    teas = [e for d in D for e in events(d, "home_new_next") if e["kind"] in ("teaser", "capture_form")]
    if not any(home_forms.values()):
        put("G1", "not_applicable", "No form to close.")
    elif not any(events(d, "home_new_next") or "category" in reached[d] for d in D):
        put("G1", "cannot_verify", "The next page after closing the form was not reached.")
    elif teas:
        put("G1", "done", "After closing the form, the next page shows: " + "; ".join(f"{e['device']} {e['kind']} \"{e['text'][:60]}\"" for e in teas[:2]), shots_of(teas))
    else:
        put("G1", "missing", "After closing the welcome form, the next page showed no teaser or tab to reopen it.")

    # G2: overlap involving a form
    ov = [e for d in D for e in devs[d]["events"] if e.get("event") == "overlap" and any(l["kind"] == "capture_form" for l in e["layers"])]
    if not all_forms:
        put("G2", "not_applicable", "No signup form seen.")
    elif ov:
        e = ov[0]
        put("G2", "missing", f"{e['device']} {e['scenario']} at {e['t_s']} s: " + " + ".join(f"{l['kind']} (\"{l['text'][:40]}\")" for l in e["layers"]), shots_of(ov))
    else:
        put("G2", "done", "The signup form never shared the screen with a cookie banner or another pop-up.")

    # H: offer
    texts = [e["text"] for e in all_forms]
    if not texts:
        for i in ("H1", "H2", "H3"):
            put(i, "not_applicable", "No signup form seen.")
    else:
        offs = [offer(t) for t in texts]
        kinds = sorted({k for o in offs for k in o["kinds"]})
        form_pct = max([o["max_pct"] for o in offs if o["max_pct"]] or [0]) or None
        put("H1", "info", f"Offer types: {', '.join(kinds)}; deepest: {str(form_pct) + '%' if form_pct else 'no % stated'}. Forms: " + " | ".join(sorted({t[:90] for t in texts}))[:500], shots_of(all_forms[:2]))
        parts = []
        for d in D:
            h = page(d, "home")
            parts += h.get("announcement_bars") or []
            parts += [h.get("top_strip_text") or "", (h.get("hero") or {}).get("text") or "", (h.get("text_signals") or {}).get("percent_off") or ""]
        site_txt = " ".join(p for p in parts if p)
        site_pcts = [int(x) for x in PCT.findall(site_txt) if 0 < int(x) < 90]
        site_pct = max(site_pcts) if site_pcts else None
        if not site_pct:
            put("H2", "not_applicable", "No % sale found in the homepage's top bar or hero.")
        elif form_pct and form_pct >= site_pct:
            put("H2", "done", f"Form offers {form_pct}%; the site sale advertises up to {site_pct}%.")
        elif any("early access" in o["kinds"] or "gift" in o["kinds"] for o in offs):
            put("H2", "done", f"The site sale is up to {site_pct}%; the form gives a different reason to sign up ({', '.join(kinds)}).")
        else:
            put("H2", "missing", f"The site advertises up to {site_pct}% (\"{site_txt.strip()[:100]}\"), the form offers {str(form_pct) + '%' if form_pct else 'no %'}.", shots_of(all_forms[:1]))
        bf = [t for t in texts if SALE_WORDS.search(t)]
        put("H3", "done" if bf else "missing", ("Sale wording in the form: \"" + bf[0][:110] + "\"") if bf else "No sale / Black Friday / early-access wording in any signup form.", shots_of(all_forms[:1]))

    # I: mechanics (facts)
    if not all_forms:
        for i in ("I1", "I2", "I3", "I4", "I5"):
            put(i, "not_applicable", "No signup form seen.")
    else:
        first_inputs = {tuple(sorted(set(e.get("inputs") or []))) for e in all_forms}
        no_field_first = [e for e in all_forms if not e.get("has_email") and not e.get("has_tel")]
        put("I1", "info", "A step before the contact field (button or question first): " + ("yes" if no_field_first else "not seen") + f". First-view inputs: {sorted(first_inputs)}.")
        put("I2", "info", "Phone field: " + ("yes" if any(e.get("has_tel") for e in all_forms) else "not on the first view"))
        put("I3", "info", "Question or choice: " + ("yes" if any(QUIZ.search(e["text"]) and not e.get("has_email") for e in all_forms) else "not seen"))
        put("I4", "info", "Game: " + ("yes" if any(GAME.search(e["text"]) for e in all_forms) else "not seen"))
        put("I5", "info", "Timer in the form: " + ("yes" if any(TIMER.search(e["text"]) for e in all_forms) else "not seen"))

    # J: test signup
    if not signup:
        for i in ("J1", "J2", "J4"):
            put(i, "cannot_verify", "The test signup was not run (signup_test.py needs the tester's own email).")
    else:
        if not signup.get("submitted"):
            put("J1", "cannot_verify", f"Test signup not submitted: {signup.get('error', 'no form reached')}.")
        else:
            code = signup.get("code_shown")
            put("J1", "done" if code else ("partial" if signup.get("check_email") else "missing"),
                f"After submit: \"{(signup.get('after_text') or '')[:160]}\"" + (f"; code {code}" if code else ""), [signup.get("after_shot")])
        lt = signup.get("consent_text")
        put("J2", "done" if lt else ("missing" if signup.get("form_found") else "cannot_verify"),
            f"Text near the field: \"{lt[:160]}\"" if lt else "No privacy / unsubscribe / SMS terms text next to the fields.", [signup.get("form_shot")])
        cr = signup.get("code_check")
        if not cr:
            put("J4", "cannot_verify", "No code was checked in the cart (run signup_test.py --code <code> on a Shopify store).")
        else:
            put("J4", "done" if cr.get("applied") else "missing", cr.get("evidence", ""), [cr.get("shot")])
    put("J3", "cannot_verify", "Needs the tester's inbox: did the welcome email arrive, how fast, with the code?")

    # K: mobile
    mf = [e for e in forms("mobile", "home_new") + forms("mobile", "product_land") + forms("mobile", "exit_cart") + forms("mobile", "browse_exit") if e.get("mobile_fit")]
    if "mobile" not in devs or not mf:
        put("K1", "not_applicable", "No signup form measured on mobile.")
        put("K2", "not_applicable", "No signup form measured on mobile.")
    else:
        e = mf[0]
        m = e["mobile_fit"]
        fails = []
        if m.get("content_fits_screen") is False:
            fails.append("content does not fit the screen")
        cb = m.get("close_button")
        if not cb:
            fails.append("no close button found")
        elif not cb.get("size_ok"):
            fails.append(f"close button {cb['box']['w']}x{cb['box']['h']} px (<24)")
        if m.get("input_font_ok") is False:
            fails.append(f"field font {m.get('input_font_px')} px (<16, iOS zooms in on tap)")
        mb = m.get("main_button")
        if mb and not mb.get("visible_without_scroll"):
            fails.append("main button below the screen")
        st = "done" if not fails else ("partial" if len(fails) == 1 else "missing")
        put("K1", st, (f"{e['scenario']}: " + ("; ".join(fails) if fails else "fits the screen, close button and field font OK, main button visible")), shots_of([e]))
        fp = next((x.get("field_position") for x in mf if x.get("field_position")), None)
        if not fp:
            put("K2", "cannot_verify", "The form's first view has no contact field to measure.")
        else:
            put("K2", "done" if fp["bottom_share"] <= 0.55 else "missing",
                f"Contact field bottom at {int(fp['bottom_share'] * 100)}% of the screen height ({fp['field_bottom']} of {fp['viewport_h']} px); the keyboard covers about the bottom 45%.", shots_of([mf[0]]))

    # L: pop-ups without a form
    nf = [e for d in D for e in devs[d]["events"] if e.get("event") == "appeared" and e["kind"] in ("other_overlay", "vendor_overlay") and not e.get("has_email") and not e.get("has_tel")
          and not NOT_A_POPUP.search(e.get("text") or "") and not GEOISH.search(e.get("text") or "")]
    uniq = {}
    for e in nf:
        uniq.setdefault(sig(e["text"]), e)
    put("L1", "info", ("; ".join(f"{e['device']} {e['scenario']}: \"{e['text'][:90]}\"" for e in uniq.values()) or "None seen."), shots_of(list(uniq.values())))

    # M: language
    alt = walk["plan"].get("other_language")
    if not alt:
        put("M1", "not_applicable", "No other language version declared (hreflang).")
    else:
        lf = forms("desktop", "lang")
        if not lf:
            put("M1", "cannot_verify", f"No signup form appeared on the {alt['lang']} homepage ({alt['href']}).")
        else:
            words = len(re.findall(r"\w+", lf[0]["text"])) or 1
            share = len(ENGLISH.findall(lf[0]["text"])) / words
            en = alt["lang"].lower().startswith("en")
            put("M1", "done" if en or share < 0.15 else "missing",
                f"{alt['lang']} homepage form: \"{lf[0]['text'][:110]}\" (English common words {int(share * 100)}%).", shots_of(lf))

    # P1: speed
    lcp = page("mobile", "home").get("lcp_ms") if "mobile" in devs else None
    if lcp is None:
        put("P1", "cannot_verify", "No LCP measured on the mobile homepage.")
    else:
        put("P1", "done" if lcp < 2500 else ("partial" if lcp <= 4000 else "missing"), f"Mobile homepage LCP {lcp / 1000:.1f} s (one lab run on the auditor's connection).")

    # D4: checkout consent
    ck = [page(d, "checkout") for d in D if page(d, "checkout")]
    if not ck:
        put("D4", "cannot_verify", "Checkout was not reached.")
    else:
        boxes = [b for c in ck for b in c.get("checkboxes", []) if re.search(r"email|news|offer|marketing|sms|text me", b["label"], re.I)]
        if not boxes:
            put("D4", "missing", "No email/SMS marketing checkbox at checkout.")
        elif any(b["checked"] for b in boxes):
            put("D4", "partial", "Marketing checkbox is pre-ticked: \"" + next(b for b in boxes if b["checked"])["label"][:100] + "\"")
        else:
            put("D4", "done", "Optional, unticked: \"" + boxes[0]["label"][:100] + "\"")

    # visual items: what to look at
    def vshots(*pairs):
        return [s["file"] for d in D for s in devs[d]["shots"] for (sc, lab) in pairs if s["scenario"] == sc and (lab is None or re.search(lab, s["label"]))]
    VIS = {
        "A": vshots(("home", "above_fold"), ("home_new", "first_view")),
        "A4": vshots(("home", "above_fold")),
        "A6": vshots(("home", "above_fold"), ("cart", "top"), ("faq", "top")),
        "B1": vshots(("category", None)), "B2": vshots(("product", None)), "B3": vshots(("product", "top"), ("category", "top")),
        "B4": vshots(("product", None)), "B5": [s["file"] for s in devs.get("mobile", {}).get("shots", []) if s["scenario"] == "product"],
        "C": vshots(("cart", None)), "D": vshots(("checkout", None)),
        "N1": vshots(("faq", None)), "N2": vshots(("home", "footer"), ("faq", "top")), "N3": vshots(("home", "footer"), ("product", "top")),
        "N4": vshots(("home", "footer"), ("home", "above_fold")),
    }
    FACTS = {
        "A": lambda d: {k: page(d, "home").get(k) for k in ("announcement_bars", "top_strip_text", "hero", "live_timers")} | {"text_signals": page(d, "home").get("text_signals")},
        "B": lambda d: {"product": {k: page(d, "product").get(k) for k in ("url", "text_signals", "apps")}, "category_tiles": (page(d, "category").get("product_tiles") or [])[:6], "walked_product": walk["plan"].get("product")},
        "C": lambda d: {k: page(d, "cart").get(k) for k in ("cart_kind", "text_signals")} | {"cart_text": ((page(d, "cart").get("checkout_view") or {}).get("text") or "")[:1500], "express": (page(d, "cart").get("checkout_view") or {}).get("express_buttons"), "add_to_cart": devs[d]["pages"].get("add_to_cart")},
        "D": lambda d: {k: page(d, "checkout").get(k) for k in ("url", "express_buttons", "login_prompt")} | {"text": (page(d, "checkout").get("text") or "")[:1500]},
        "N": lambda d: {"faq": {k: page(d, "faq").get(k) for k in ("url", "title", "faq", "text_signals")}, "footer": page(d, "home").get("footer"), "payment_icons": page(d, "home").get("payment_icons"), "apps": page(d, "home").get("apps")},
    }
    items = []
    for it in CHECKLIST["items"]:
        r = {"id": it["id"], "block": it["block"], "title": it["title"], "judge": it["judge"]}
        if it["id"] in res:
            r.update(res[it["id"]])
        elif it["judge"] == "visual":
            sh = VIS.get(it["id"]) or VIS.get(it["block"]) or []
            r.update({"status": None, "evidence": "", "screenshots_to_view": sh[:8],
                      "facts": {d: FACTS[it["block"]](d) for d in D if it["block"] in FACTS}})
        else:
            r.update({"status": None, "evidence": ""})
        items.append(r)
    draft = {"site": walk["site"], "walked_utc": walk["started_utc"], "plan": walk["plan"],
             "walk_errors": {d: devs[d]["errors"] for d in D}, "items": items}
    (out / "draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
    todo = [i["id"] for i in items if i["status"] is None]
    print(f"draft.json: {len(items) - len(todo)} items judged from measurements, {len(todo)} to judge from screenshots: {', '.join(todo)}")


if __name__ == "__main__":
    main()
