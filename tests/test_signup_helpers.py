import asyncio

from playwright.async_api import async_playwright

import signup_test
import walk
from conftest import MOBILE
from pages import claspo_box, page


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        tab = await browser.new_page(viewport=MOBILE)
        await tab.set_content(page(claspo_box("Get 10% off your first order", "Get 10%")))
        await tab.wait_for_timeout(150)
        pa_id = (await tab.evaluate(walk.JS["detect"]))["overlays"][0]["pa_id"]
        first = await tab.evaluate(signup_test.FORM_JS, pa_id)
        opened = await tab.evaluate(signup_test.OPEN_JS, pa_id)
        await tab.wait_for_timeout(150)
        second = await tab.evaluate(signup_test.FORM_JS, pa_id)
        filled = await tab.evaluate(signup_test.FILL_JS, [pa_id, "tester@example.com"])
        await browser.close()
        return first, opened, second, filled


def test_form_open_and_fill_reach_nested_fields():
    first, opened, second, filled = asyncio.run(run())
    assert first["has_email"] is False
    assert "Get 10% off your first order" in first["text"]
    assert opened == "Get 10%"
    assert second["has_email"] is True
    assert "Enter your email" in second["text"]
    assert filled == "clicked: Subscribe"
