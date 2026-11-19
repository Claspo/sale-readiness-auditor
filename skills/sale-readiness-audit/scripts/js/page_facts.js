// Reads what a shopper can see on the current page, by page zone, for the BFCM CRO checklist.
// Returns plain facts (texts, links, flags); the judging is done later against screenshots.
() => {
  const W = innerWidth, H = innerHeight;
  const vis = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05;
  };
  const txt = (el, n = 400) => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const absTop = el => el.getBoundingClientRect().top + scrollY;
  const cls = el => (typeof el.className === 'string' ? el.className : (el.getAttribute && el.getAttribute('class')) || '');
  const sig = el => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}.${cls(el).split(/\s+/).slice(0, 3).join('.')}`;
  const linksOf = (root, n = 60) => [...root.querySelectorAll('a[href]')].filter(vis).slice(0, n)
    .map(a => ({t: txt(a, 60) || a.getAttribute('aria-label') || '', h: a.getAttribute('href')}));
  const q = s => [...document.querySelectorAll(s)];
  const body = document.body;
  const pageH = Math.max(body.scrollHeight, document.documentElement.scrollHeight);

  // --- header & announcement bar ---------------------------------------------------------
  let header = document.querySelector('header, [role=banner], #shopify-section-header, .site-header, .header');
  const topBars = q('[class*="announcement"], [id*="announcement"], [class*="promo-bar"], [class*="top-bar"], [class*="topbar"], [class*="ticker"], [class*="marquee"]')
    .filter(el => vis(el) && absTop(el) < 250).slice(0, 4).map(el => txt(el, 300));
  const topStrip = (() => { const el = document.elementFromPoint(W / 2, 8); let p = el;
    for (let i = 0; i < 6 && p && p.parentElement && p.getBoundingClientRect().height < 25; i++) p = p.parentElement;
    return p && p !== document.body ? txt(p, 200) : null; })();
  const headerInfo = header ? {
    selector: sig(header), text: txt(header, 800), links: linksOf(header, 80),
    position: getComputedStyle(header).position,
    search_placeholders: [...header.querySelectorAll('input[type=search], input[name=q], input[placeholder]')].map(i => i.placeholder).filter(Boolean),
  } : null;
  const searchPlaceholders = q('input[type=search], input[name=q]').map(i => i.placeholder).filter(Boolean).slice(0, 3);

  // --- icons / switchers in the header area ---------------------------------------------
  const topEls = q('a, button, select, form').filter(el => vis(el) && el.getBoundingClientRect().top < 200);
  const topLabel = el => (txt(el, 40) + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('href') || '') + ' ' + cls(el)).toLowerCase();
  const has = re => topEls.some(el => re.test(topLabel(el)));
  const headerIcons = {
    wishlist: has(/wish ?list|favou?rite|heart|saved/),
    account: has(/account|login|sign in|log in/),
    cart: has(/cart|bag|basket/),
    track_order: has(/track/),
    search: has(/search/),
    localization: q('form[action*="localization"], [class*="localization"], [class*="currency"], [class*="country-selector"], [class*="language"], select[name*="currency"]').some(vis),
  };
  const cartCountEl = q('[class*="cart-count"], [class*="cart_count"], [class*="cart-count-bubble"], [data-cart-count], .cart-count, #CartCount').find(vis);

  // --- above the fold / hero --------------------------------------------------------------
  const headerBottom = header && vis(header) ? header.getBoundingClientRect().bottom + scrollY : 0;
  const foldCtas = q('a, button').filter(el => {
    if (!vis(el)) return false; const r = el.getBoundingClientRect();
    return r.top + scrollY > headerBottom && r.top + scrollY < H && txt(el, 50).length > 1;
  }).slice(0, 15).map(el => txt(el, 50));
  const heroCandidates = q('main section, main > div, [class*="hero"], [class*="slideshow"], [class*="banner"], [id*="hero"], [class*="carousel"]')
    .filter(el => vis(el) && el !== body && absTop(el) >= headerBottom - 5 && absTop(el) < H && el.getBoundingClientRect().height > 200 && el.getBoundingClientRect().height < H * 1.6);
  const hero = heroCandidates[0] || null;
  const heroInfo = hero ? {
    selector: sig(hero), text: txt(hero, 600),
    has_video: !!hero.querySelector('video, iframe[src*="youtube"], iframe[src*="vimeo"]'),
    video: [...hero.querySelectorAll('video')].map(v => ({autoplay: v.autoplay, muted: v.muted, loop: v.loop, tracks: v.querySelectorAll('track').length})),
    slides: hero.querySelectorAll('[class*="slide"]:not([class*="slides"]), .swiper-slide, .flickity-cell, .slick-slide').length,
    links: linksOf(hero, 20),
  } : null;
  const animated = q('*').slice(0, 4000).filter(el => {
    const cs = getComputedStyle(el); return vis(el) && cs.animationName && cs.animationName !== 'none' && absTop(el) < H * 1.2;
  }).slice(0, 6).map(sig);

  // --- page sections in order ---------------------------------------------------------------
  const sections = q('main > *, main section, [id^="shopify-section"], body > section')
    .filter(el => vis(el) && el.getBoundingClientRect().height > 60)
    .filter((el, i, arr) => !arr.some((o, j) => j !== i && o !== el && o.contains(el) && arr.indexOf(o) < i))
    .slice(0, 40)
    .map(el => ({sel: sig(el), y: Math.round(absTop(el)), h: Math.round(el.getBoundingClientRect().height),
      headings: [...el.querySelectorAll('h1,h2,h3')].filter(vis).slice(0, 4).map(h => txt(h, 80)),
      text: txt(el, 260)}));

  // --- product tiles ------------------------------------------------------------------------
  const tileLinks = q('a[href*="/products/"], a[href*="/product/"], a[href*="/p/"]').filter(vis);
  const tiles = [];
  const seen = new Set();
  for (const a of tileLinks) {
    let t = a; for (let i = 0; i < 6 && t.parentElement; i++) { if (/\d[.,]\d{2}|\$|€|£|₴|zł|kr/.test(txt(t.parentElement, 300)) && t.parentElement.querySelectorAll('a[href*="/products/"], a[href*="/product/"]').length <= 3) t = t.parentElement; else break; }
    if (seen.has(t)) continue; seen.add(t);
    const tt = txt(t, 300);
    if (!/\d/.test(tt)) continue;
    tiles.push({
      text: tt,
      href: a.getAttribute('href'),
      strike_price: !!t.querySelector('s, del, [class*="compare"], [class*="was-price"], [class*="price--regular"], [class*="original"]'),
      quick_add: [...t.querySelectorAll('button, [role=button], form[action*="/cart/add"]')].some(b => /add|quick|\+|cart|bag/i.test(txt(b, 40) + ' ' + (b.getAttribute && (b.getAttribute('aria-label') || '')) + ' ' + (b.getAttribute && (b.getAttribute('action') || '')))),
      swatches: t.querySelectorAll('[class*="swatch"], [class*="color-option"], [class*="colour"]').length,
      rating: !!t.querySelector('[class*="rating"], [class*="stars"], [class*="review"], .jdgm-preview-badge, .yotpo, .okeReviews, .loox-rating, .stamped-badge'),
      badges: [...t.querySelectorAll('[class*="badge"], [class*="label"], [class*="tag"], [class*="ribbon"]')].filter(vis).map(b => txt(b, 40)).filter(Boolean).slice(0, 4),
      images: t.querySelectorAll('img').length,
      wishlist: !!t.querySelector('[class*="wishlist"], [class*="favorite"], [class*="heart"]'),
    });
    if (tiles.length >= 16) break;
  }

  // --- category tiles -----------------------------------------------------------------------
  const catTiles = q('a[href*="/collections/"], a[href*="/category/"], a[href*="/c/"]').filter(el => vis(el) && el.querySelector('img') && absTop(el) > headerBottom)
    .slice(0, 16).map(a => ({text: txt(a, 120), href: a.getAttribute('href')}));

  // --- trust, reviews, payments, social -----------------------------------------------------
  const imgs = q('img, svg').filter(vis);
  const imgLabel = el => ((el.getAttribute('alt') || '') + ' ' + (el.getAttribute('src') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + ((el.querySelector && el.querySelector('title') && el.querySelector('title').textContent) || '') + ' ' + cls(el)).toLowerCase();
  const PAY = /visa|mastercard|master card|amex|american express|paypal|apple ?pay|google ?pay|shop ?pay|klarna|afterpay|clearpay|maestro|discover|diners|jcb|union ?pay|ideal|bancontact|sofort|twint|blik|affirm|sezzle|venmo|meta ?pay|amazon ?pay|elo|mir/;
  const payment_icons = [...new Set(imgs.map(imgLabel).map(l => (l.match(PAY) || [])[0]).filter(Boolean))];
  const trust_badges = imgs.map(imgLabel).filter(l => /secure|ssl|norton|mcafee|trusted|guarantee|money[- ]back|badge|certif|award|verified|bbb|trustpilot/.test(l)).slice(0, 12).map(l => l.slice(0, 90));
  const pageText = txt(body, 60000);
  const lower = pageText.toLowerCase();
  const kw = re => { const m = lower.match(re); if (!m) return null; const i = m.index; return pageText.slice(Math.max(0, i - 60), i + 90); };
  const scripts = q('script[src]').map(s => s.src).concat(q('link[href]').map(l => l.href)).join(' ').toLowerCase();
  const html = document.documentElement.outerHTML.slice(0, 400000).toLowerCase();
  const APPS = {
    judgeme: /judge\.me|jdgm/, yotpo: /yotpo/, okendo: /okendo/, loox: /loox/, stamped: /stamped\.io/, trustpilot: /trustpilot/,
    reviews_io: /reviews\.io|reviewsio/, junip: /junip/, feefo: /feefo/, bazaarvoice: /bazaarvoice/, google_reviews: /google customer reviews|merchantwidget/,
    klaviyo: /klaviyo/, attentive: /attn\.tv|attentive/, privy: /privy/, justuno: /justuno/, omnisend: /omnisend/, claspo: /claspo/,
    gorgias: /gorgias/, intercom: /intercom/, zendesk: /zdassets|zendesk/, tidio: /tidio/, shopify_inbox: /shopify-chat|inbox\.shopify/, livechat: /livechatinc/, freshchat: /freshchat|freshworks/, richpanel: /richpanel/,
    fomo_social_proof: /fomo\.com|usefomo|salespop|proofapp|nudgify|provesource|sales-notification|sales_pop/,
    rebuy: /rebuy/, upcart: /upcart/, smile_loyalty: /smile\.io/, yotpo_loyalty: /swell|yotpo-loyalty/, loyaltylion: /loyaltylion/, rivo: /rivo/,
    countdown_app: /countdown|timer/, wishlist_app: /wishlist/, recently_viewed: /recently[-_ ]viewed/, langify_weglot: /weglot|langify|transcy/,
  };
  const apps = Object.entries(APPS).filter(([k, re]) => re.test(scripts) || (k !== 'countdown_app' && k !== 'wishlist_app' && re.test(html))).map(([k]) => k);

  // --- footer -------------------------------------------------------------------------------
  const footer = q('footer, [role=contentinfo], #shopify-section-footer, .site-footer').filter(vis).pop() || null;
  const footerInfo = footer ? {
    selector: sig(footer), text: txt(footer, 2500), links: linksOf(footer, 120),
    newsletter_form: !!footer.querySelector('input[type=email], input[name*="email"]'),
    social: [...new Set([...footer.querySelectorAll('a[href]')].map(a => (a.href.match(/(instagram|facebook|tiktok|youtube|pinterest|twitter|x\.com|linkedin|threads)/) || [])[1]).filter(Boolean))],
    app_badges: !!footer.querySelector('a[href*="apps.apple.com"], a[href*="play.google.com"]'),
    phone: (txt(footer, 4000).match(/(\+?\d[\d\s().-]{7,}\d)/) || [null])[0],
    country_flags: footer.querySelectorAll('img[src*="flag"], [class*="flag"]').length,
  } : null;

  // --- FAQ ----------------------------------------------------------------------------------
  const faqEls = q('details, [class*="faq"], [id*="faq"], [class*="accordion"], [class*="collapsible"]').filter(vis);
  const faq = {
    on_page: faqEls.length > 0 || /frequently asked|faq/.test(lower),
    questions: q('details summary, [class*="faq"] button, [class*="faq"] h3, [class*="faq"] h4, [class*="accordion"] button, [class*="collapsible"] button, [class*="accordion"] summary')
      .filter(vis).map(el => txt(el, 140)).filter(t => t.length > 6).slice(0, 60),
    search_box: !!document.querySelector('[class*="faq"] input, [class*="help"] input[type=search]'),
    video: !!document.querySelector('[class*="faq"] video, [class*="faq"] iframe'),
    links: q('a[href]').filter(a => /faq|help|support|frequently/i.test(a.getAttribute('href') + ' ' + txt(a, 40))).slice(0, 6).map(a => a.href),
  };

  // --- generic signals in page text ---------------------------------------------------------
  const timerish = q('*').filter(el => el.children.length < 12 && vis(el) && /\b\d{1,2}\s*[:hдd]\s*\d{1,2}\s*[:mм]\s*\d{1,2}/i.test(txt(el, 60)) && txt(el, 200).length < 120).slice(0, 5).map(el => ({sel: sig(el), text: txt(el, 100), y: Math.round(absTop(el))}));

  return {
    url: location.href, title: document.title, lang: document.documentElement.lang || null,
    viewport: [W, H], page_height: pageH,
    platform: {shopify: !!(window.Shopify && window.Shopify.shop), shop: window.Shopify && window.Shopify.shop, currency: window.Shopify && window.Shopify.currency && window.Shopify.currency.active,
      woocommerce: /woocommerce/.test(html), bigcommerce: /bigcommerce/.test(html), magento: /mage\/|magento/.test(html)},
    announcement_bars: topBars, top_strip_text: topStrip, header: headerInfo, search_placeholders: searchPlaceholders, header_icons: headerIcons,
    cart_count_badge: cartCountEl ? txt(cartCountEl, 20) : null,
    above_fold_ctas: foldCtas, hero: heroInfo, animated_near_top: animated,
    sections, product_tiles: tiles, category_tiles: catTiles,
    payment_icons, trust_badges, apps, footer: footerInfo, faq, timer_like_text: timerish,
    text_signals: {
      bfcm: kw(/black friday|cyber monday|bfcm|black week|cyber week|singles day|thanksgiving/),
      percent_off: kw(/\d{1,2}\s?% (off|discount)|save \d{1,2}\s?%|up to \d{1,2}\s?%/),
      free_shipping: kw(/free (shipping|delivery)|kostenlose?r? versand|livraison gratuite|envío gratis/),
      free_gift: kw(/free gift|gift with purchase|gwp/),
      returns: kw(/(free|easy|\d+[- ]day) returns?|return policy|money[- ]back/),
      guarantee: kw(/guarantee|warranty/),
      reviews_count: kw(/\d[\d,.]*\+?\s*(reviews|ratings|customers|happy customers|5[- ]star)/),
      sold_or_viewing: kw(/\d+\s*(people )?(are )?(viewing|watching|sold|bought|purchased)/),
      low_stock: kw(/only \d+ left|low stock|almost (gone|sold out)|selling fast|limited stock/),
      vip_loyalty: kw(/vip|early access|loyalty|rewards|points|members?/),
      gift_guide: kw(/gift guide|gifts? for (him|her)|gifts? under/),
      press: kw(/as seen (in|on)|featured in|press/),
      sustainability: kw(/sustainab|carbon|eco[- ]friendly|recycled|planet|charity|donat/),
      delivery_estimate: kw(/(arrives|delivery|delivered|get it) (by|on|between)|estimated delivery|ships (in|within|today)/),
      shipping_cutoff: kw(/order by|cut-?off|last day to order|in time for (christmas|the holidays)/),
      size_guide: kw(/size (guide|chart)|fit guide/),
      chat: kw(/live chat|chat with us|chat now/),
      klarna_bnpl: kw(/klarna|afterpay|clearpay|pay in (4|3)|interest-free/),
      careers: kw(/careers|jobs|we.?re hiring/),
      accessibility: kw(/accessibility/),
      store_locator: kw(/store locator|find a store|our stores/),
      affiliate: kw(/affiliate|partner program|ambassador/),
      company_legal: kw(/(ltd|llc|gmbh|inc\.|vat|company (no|number)|registered)/),
    },
  };
}
