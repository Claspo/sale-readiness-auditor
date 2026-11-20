import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.async_api import async_playwright

import walk
from pages import PIXEL, product_cards

HEADER = """<header>
  <a href="/ua/customer/account/">Акаунт</a><a href="/ua/help/">Допомога</a><a href="/ua/checkout/cart/">Кошик</a>
  <nav><a href="/ua/women/">Жінкам</a><a href="/ua/men/">Чоловікам</a><a href="/ua/outlet/">Аутлет</a></nav>
</header>"""


def html(body: str, head: str = "") -> bytes:
    return (f"<!doctype html><html lang='uk'><head><meta charset='utf-8'>{head}"
            f"<script type='text/x-magento-init'>{{}}</script></head><body>{HEADER}<main>{body}</main></body></html>").encode()


def product_page(i: int) -> bytes:
    ld = {"@context": "https://schema.org", "@type": "Product", "name": f"Сукня {i}",
          "offers": {"@type": "Offer", "price": f"249{i}", "priceCurrency": "UAH"}}
    return html(f"<h1>Сукня {i}</h1><img src='{PIXEL}' width='400' height='500'><span class='price'>2 49{i} грн</span>"
                f"<button id='product-addtocart-button' type='submit'>Додати в кошик</button>",
                head=f"<script type='application/ld+json'>{json.dumps(ld)}</script>")


ROUTES = {
    "/": html("<h2>Нова колекція</h2>"),
    "/ua/women/": html(product_cards(6)),
    "/ua/men/": html(product_cards(6)),
    "/ua/outlet/": html(product_cards(6)),
    **{f"/ua/dress-{i}.html": product_page(i) for i in range(1, 7)},
}


SHOPIFY_HEADER = "<header><a href='/cart'>Cart</a><nav><a href='/collections/dresses'>Dresses</a><a href='/pages/about'>About</a></nav></header>"


def shopify_html(body: str) -> bytes:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><script>window.Shopify = {{shop: 'test.myshopify.com'}};</script>"
            f"</head><body>{SHOPIFY_HEADER}<main>{body}</main></body></html>").encode()


SHOPIFY_CARDS = "".join(f"<div class='card'><a href='/products/dress-{i}'><img src='{PIXEL}' width='200' height='260'></a>"
                        f"<a href='/products/dress-{i}'>Dress {i}</a><span>$4{i}.00</span></div>" for i in range(1, 7))
SHOPIFY_ROUTES = {
    "/": shopify_html("<h2>New in</h2>"),
    "/collections/dresses": shopify_html(SHOPIFY_CARDS),
    "/products.json?limit=50": json.dumps({"products": [{"handle": f"dress-{i}", "product_type": "Dress"} for i in range(1, 7)]}).encode(),
    **{f"/products/dress-{i}.js": json.dumps({"title": f"Dress {i}", "variants": [
        {"id": 1000 + i, "available": True, "price": 4000 + i * 100, "compare_at_price": 6000}]}).encode() for i in range(1, 7)},
}


def serve(routes):
    class Store(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = routes.get(self.path)
            self.send_response(200 if body else 404)
            json_like = self.path.endswith(".js") or ".json" in self.path
            self.send_header("Content-Type", "application/json" if json_like else "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body or b"not found")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Store)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def store():
    server = serve(ROUTES)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def shopify_store():
    server = serve(SHOPIFY_ROUTES)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def discover(base):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            return await walk.discover(browser, base)
        finally:
            await browser.close()


def test_store_without_shopify_urls(store):
    plan = asyncio.run(discover(store + "/"))
    assert plan["category"] == store + "/ua/outlet/"
    assert plan["product"]["url"].startswith(store + "/ua/dress-")
    assert plan["product"]["url"].endswith(".html")
    assert len(plan["browse"]) == 3
    assert plan["cart"] == store + "/ua/checkout/cart/"


def test_shopify_store_keeps_the_cart_api_product(shopify_store):
    plan = asyncio.run(discover(shopify_store + "/"))
    assert plan["category"] == shopify_store + "/collections/dresses"
    assert plan["product"]["url"] == shopify_store + "/products/dress-1"
    assert plan["product"]["variant_id"] == 1001
    assert plan["product"]["discounted"] is True
    assert plan["cart"] == shopify_store + "/cart"
    assert len(plan["browse"]) == 3
