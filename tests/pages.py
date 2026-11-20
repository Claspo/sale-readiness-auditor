"""Synthetic store pages for the tests. They copy the structure the scripts meet in the wild, not any store's content.

Claspo widgets render each component in its own open shadow root, nested inside the widget's shadow host,
and mark the layout element with a `cl-widget-id` attribute. A two-step form shows a button first and the
email field only after that button is clicked.
"""

PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="

COMPONENTS = """<script>
const plain = (name, html) => customElements.define(name, class extends HTMLElement {
  constructor() { super(); this.attachShadow({mode: 'open'}).innerHTML = html(this); } });
plain('x-text', el => `<p style="margin:0 0 8px;font:16px sans-serif">${el.getAttribute('t')}</p>`);
plain('x-email', () => '<input type="email" name="email" placeholder="Email" style="width:300px;height:40px;font-size:16px">');
customElements.define('x-button', class extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `<button style="width:300px;height:48px">${this.getAttribute('t')}</button>`;
    this.shadowRoot.querySelector('button').addEventListener('click',
      () => this.dispatchEvent(new CustomEvent('x-next', {bubbles: true, composed: true})));
  }
});
</script>"""

OPAQUE_MAIN = "<main style='position:relative;z-index:0;height:3000px;background:#fff'><h1>Store</h1></main>"


def page(*parts: str, body: str = OPAQUE_MAIN, lang: str = "en") -> str:
    return (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>{COMPONENTS}</head>"
            f"<body style='margin:0'>{body}{''.join(parts)}</body></html>")


def claspo_box(title: str, button: str, step2: str = "Enter your email", widget_id: str = "1001",
               width: int = 379, height: int = 214) -> str:
    """A floating box at the bottom of a phone screen: 379x214 px is 24.6 % of a 390x844 viewport."""
    return f"""
<div class="cl-floating-box" cl-widget-id="{widget_id}"
     style="position:fixed;left:0;bottom:0;width:{width}px;height:{height}px;z-index:2147483000;background:#fff">
  <div class="cl-floating-box-close-icon" style="position:absolute;right:4px;top:4px;width:28px;height:28px">x</div>
  <div class="cl-floating-box-content"><es-sys-container-static></es-sys-container-static></div>
</div>
<script>
(() => {{
  const host = document.currentScript.previousElementSibling.querySelector('es-sys-container-static');
  const root = host.attachShadow({{mode: 'open'}});
  root.innerHTML = '<div><x-text t="{title}"></x-text><x-button t="{button}"></x-button></div>';
  root.addEventListener('x-next', () => {{
    root.innerHTML = '<div><x-text t="{step2}"></x-text><x-email></x-email><x-button t="Subscribe"></x-button></div>';
  }});
}})();
</script>"""


def claspo_launcher(label: str, widget_id: str = "1002") -> str:
    return f"""
<div class="cl-launcher" cl-widget-id="{widget_id}"
     style="position:fixed;right:0;bottom:300px;width:120px;height:44px;z-index:2147483000;background:#000">
  <es-sys-container-static></es-sys-container-static>
</div>
<script>
(() => {{
  const host = document.currentScript.previousElementSibling.querySelector('es-sys-container-static');
  host.attachShadow({{mode: 'open'}}).innerHTML = '<x-text t="{label}"></x-text>';
}})();
</script>"""


def claspo_promo_link(title: str, link_text: str, href: str) -> str:
    """A vendor pop-up whose only button is a link to another page: an announcement, not a form."""
    return f"""
<div class="cl-dialog" cl-widget-id="1003"
     style="position:fixed;left:20px;top:200px;width:350px;height:300px;z-index:2147483000;background:#fff">
  <es-sys-container-static></es-sys-container-static>
</div>
<script>
(() => {{
  const host = document.currentScript.previousElementSibling.querySelector('es-sys-container-static');
  host.attachShadow({{mode: 'open'}}).innerHTML =
    '<x-text t="{title}"></x-text><a href="{href}" style="display:block;width:300px;height:48px">{link_text}</a>';
}})();
</script>"""


HIDDEN_CART_DRAWER = """
<div class="minicart" style="position:fixed;inset:0;z-index:-1;background:#fafafa">
  <h2>Cart</h2><p>Your cart is empty. Add products to the cart from a product page.</p>
</div>"""

# The same drawer as many themes ship it: no pointer events while closed, its panel slid off-screen.
HIDDEN_CART_DRAWER_NO_POINTER = """
<aside class="mini-cart" style="position:fixed;inset:0;z-index:-1;pointer-events:none">
  <div style="width:100%;height:100%;transform:translateX(125%);background:#fafafa;pointer-events:none">
    <h2>Cart</h2><p>Your cart is empty. Add products to the cart from a product page.</p>
  </div>
</aside>"""

COUNTRY_PICKER_UNDER_CONSENT = """
<div style="position:fixed;left:15px;top:250px;width:360px;height:260px;z-index:1000;background:#fff">
  <p>Choose your country to see local prices</p><button>Continue</button>
</div>
<div style="position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.4)">
  <div style="position:absolute;left:0;right:0;bottom:0;height:200px;background:#fff">
    <p>We use cookies to improve your experience.</p><button>Accept</button>
  </div>
</div>"""

FOREIGN_CL_CLASSES = """
<div class="cl-rootBox cl-signIn-root" style="position:fixed;left:20px;top:80px;width:350px;height:600px;background:#fff">
  <p>Sign in to continue to your account</p><button>Continue with email</button>
</div>"""


def product_cards(n: int = 6, *, magento: bool = True, currency: str = "грн") -> str:
    """Category grid of a store with plain product URLs (`/ua/dress-1.html`, `/catalog/item-101`)."""
    cards = []
    for i in range(1, n + 1):
        if magento:
            href = f"/ua/dress-{i}.html"
            cards.append(f'<li class="item product product-item"><div class="product-item-info">'
                         f'<a href="{href}" class="product photo product-item-photo"><img src="{PIXEL}" width="200" height="260" alt="Dress {i}"></a>'
                         f'<div class="product-item-details"><strong class="product-item-name"><a class="product-item-link" href="{href}">Сукня {i}</a></strong>'
                         f'<span class="price">2 49{i} {currency}</span></div></div></li>')
        else:
            href = f"/catalog/item-10{i}"
            cards.append(f'<div><a href="{href}"><img src="{PIXEL}" width="200" height="200" alt=""></a>'
                         f'<a href="{href}">Шапка {i}</a><div>1 29{i} {currency}</div></div>')
    grid = "".join(cards)
    return f"<ol class='products list items product-items'>{grid}</ol>" if magento else f"<div style='display:grid'>{grid}</div>"


def category_tiles(n: int = 4) -> str:
    """Homepage tiles that link to categories: an image and a name, no price."""
    return "".join(f'<a href="/ua/cat-{i}/"><img src="{PIXEL}" width="300" height="200" alt="">Категорія {i}</a>' for i in range(n))
