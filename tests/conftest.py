import asyncio
import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "sale-readiness-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

MOBILE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}


def js(name: str) -> str:
    return (SCRIPTS / "js" / f"{name}.js").read_text(encoding="utf-8")


async def _evaluate(html: str, script: str, viewport: dict):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport=viewport)
        await page.set_content(html)
        await page.wait_for_timeout(150)
        result = await page.evaluate(script)
        await browser.close()
        return result


@pytest.fixture
def run_js():
    def run(html: str, name: str, viewport: dict = MOBILE):
        return asyncio.run(_evaluate(html, js(name), viewport))
    return run
