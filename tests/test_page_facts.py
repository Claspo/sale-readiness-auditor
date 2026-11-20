from conftest import DESKTOP
from pages import category_tiles, page, product_cards


def facts(run_js, body, lang="uk"):
    return run_js(page(body=f"<main>{body}</main>", lang=lang), "page_facts", DESKTOP)


def test_product_tiles_with_html_urls_and_hryvnia_prices(run_js):
    tiles = facts(run_js, product_cards(6, magento=True))["product_tiles"]
    assert len(tiles) == 6
    assert all(t["href"].endswith(".html") for t in tiles)


def test_product_tiles_without_platform_classes(run_js):
    tiles = facts(run_js, product_cards(5, magento=False, currency="₴"))["product_tiles"]
    assert [t["href"] for t in tiles] == [f"/catalog/item-10{i}" for i in range(1, 6)]


def test_category_tiles_without_prices_are_not_products(run_js):
    assert facts(run_js, category_tiles(4))["product_tiles"] == []


def test_ukrainian_sale_signals(run_js):
    signals = facts(run_js, "<p>Чорна п'ятниця: знижки до −30% на все. Безкоштовна доставка від 2000 грн.</p>")["text_signals"]
    assert signals["bfcm"]
    assert signals["percent_off"]
    assert signals["free_shipping"]
