import asyncio

from playwright.async_api import async_playwright

import walk
from pages import claspo_box, claspo_promo_link, page


async def watch(html, out):
    (out / "shots").mkdir()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        dev = walk.Device(browser, "mobile", "https://store.test", out, {})
        ctx, tab = await dev.context()
        await tab.set_content(html)
        await dev.watch(tab, "home_new", 6, scroll=False, hands_off=99, close_after=False)
        url = tab.url
        await ctx.close()
        await browser.close()
    return [e for e in dev.events if e.get("event") == "appeared"], url


def test_two_step_form_is_opened_and_counted_once(tmp_path):
    events, _ = asyncio.run(watch(page(claspo_box("Get 10% off your first order", "Get 10%")), tmp_path))
    forms = [e for e in events if e["kind"] == "capture_form"]
    assert len(forms) == 1
    form = forms[0]
    assert form["two_step"] is True
    assert form["has_email"] is True
    assert "Get 10% off your first order" in form["text"]
    assert "Enter your email" in form["next_step_text"]
    assert form["mobile_fit"]["input_font_ok"] is True
    assert form["field_position"]["field_bottom"] > 0


def test_link_to_another_page_is_never_clicked(tmp_path):
    html = page(claspo_promo_link("Black Friday: up to 30% off everything", "Shop the sale", "https://example.com/sale"))
    events, url = asyncio.run(watch(html, tmp_path))
    assert [e["kind"] for e in events] == ["vendor_overlay"]
    assert url == "about:blank"


def test_purchase_buttons_are_never_clicked(tmp_path):
    events, _ = asyncio.run(watch(page(claspo_box("Complete the look: 15% off this bag", "Add to cart")), tmp_path))
    assert [e["kind"] for e in events] == ["vendor_overlay"]
    assert "next_step_text" not in events[0]
