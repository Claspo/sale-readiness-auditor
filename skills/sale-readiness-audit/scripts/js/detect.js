// Returns every overlay a visitor can actually see on top of the page: popups, cookie banners, teasers, flyouts.
// Runs in the page every ~500 ms; Python diffs the results to log appear/disappear events.
// Instead of scanning the whole DOM it probes a grid of screen points and takes the fixed-position
// ancestor of whatever is on top there. Hidden modals, galleries waiting off-screen and layers that
// are covered by something else never hit, which removes most false positives and keeps it cheap.
() => {
  const vw = innerWidth, vh = innerHeight, va = vw * vh;
  const VENDORS = [
    ['klaviyo', /klaviyo|kl-private|kl-teaser/i],
    ['privy', /privy/i], ['justuno', /justuno|jx-/i], ['omnisend', /omnisend/i],
    ['optimonk', /optimonk|om-holder/i], ['wisepops', /wisepops/i], ['poptin', /poptin/i],
    ['attentive', /attentive|attn\.tv/i], ['postscript', /postscript|ps-desktop|ps-mobile/i],
    ['sumo', /sumo-|sumome/i], ['getsitecontrol', /getsitecontrol|gsc-/i], ['sleeknote', /sleeknote/i],
    ['amped', /\bamped[-_.]/i], ['wheelio', /wheelio/i], ['mailchimp', /mc-modal|mailchimp/i],
    ['shopify_forms', /shopify-forms|forms\.shopifyapps/i], ['claspo', /claspo/i], ['alia', /\balia-app\b/],
  ];
  const COOKIE = /cookie|consent|gdpr|privacy (settings|preferences)|we use (cookies|technologies)/i;
  // "we don't ship to your country" / country pickers: the store answering the crawler's IP, not the imitated market
  const GEO = /(ship|deliver)(s|ping)? to your (country|region|location)|you('re| are) (visiting|browsing|shopping) from|choose your (country|region|location)|select your (country|region|location)/i;
  const shown = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.05; };

  // probe points: 6x6 grid + points hugging edges and corners (teasers, cookie bars, flyouts live there)
  const pts = [];
  for (let i = 1; i <= 6; i++) for (let j = 1; j <= 6; j++) pts.push([vw * i / 7, vh * j / 7]);
  for (const x of [25, 60, vw / 2, vw - 60, vw - 25]) for (const y of [25, 60, vh - 60, vh - 25]) pts.push([x, y]);

  // Every element stacked under a point, not just the top one, so a modal covered by another layer's
  // backdrop still counts; open shadow roots (consent tools use them) are searched too.
  const stackAt = (root, x, y, depth = 0) => {
    const out = [];
    for (const el of root.elementsFromPoint(x, y)) {
      out.push(el);
      if (el.shadowRoot && depth < 3) out.push(...stackAt(el.shadowRoot, x, y, depth + 1).filter(e => e !== el));
    }
    return out;
  };
  const up = n => n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
  // Every visible fixed layer on the page, including ones inside open shadow roots and ones covered by
  // another layer (a country picker under a consent backdrop cannot be clicked, so point probes miss it).
  // A zero-size custom-element host (consent tools) does not count; its sized fixed child does.
  const allEls = [];
  const collect = (root, depth = 0) => {
    for (const el of root.querySelectorAll('*')) {
      allEls.push(el);
      if (el.shadowRoot && depth < 3) collect(el.shadowRoot, depth + 1);
    }
  };
  collect(document.body);
  const sized = el => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw; };
  const visibleNow = el => (el.checkVisibility ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) : true) && sized(el);
  const fixedLayers = [];
  for (const el of allEls) {
    if (getComputedStyle(el).position !== 'fixed' || !visibleNow(el)) continue;
    let covered = false;
    for (let n = up(el); n && n !== document.body; n = up(n)) {
      if (n.nodeType === 1 && getComputedStyle(n).position === 'fixed' && sized(n)) { covered = true; break; }
    }
    if (!covered) fixedLayers.push(el);  // outermost sized fixed layer
  }
  const hosts = new Map(fixedLayers.map(el => [el, false]));
  // on top = the first layer met in the stack under any probe point (shadow hosts are skipped through)
  const layerOf = e => fixedLayers.find(el => el === e || el.contains(e));
  for (const [x, y] of pts) {
    for (const e of stackAt(document, x, y)) {
      const hit = layerOf(e);
      if (hit) { hosts.set(hit, true); break; }
      if (!e.shadowRoot) break;  // a page element is on top here
    }
  }
  // shadow roots carry their own <style>; only the rendered text counts
  const deepText = el => ((el.innerText || '') + ' ' + [el, ...el.querySelectorAll('*')].filter(n => n.shadowRoot)
    .map(n => [...n.shadowRoot.children].filter(c => !/^(STYLE|SCRIPT|LINK)$/.test(c.tagName)).map(c => c.innerText || c.textContent || '').join(' ')).join(' '));
  const deepAll = (el, sel) => [...el.querySelectorAll(sel), ...[el, ...el.querySelectorAll('*')].filter(n => n.shadowRoot).flatMap(n => [...n.shadowRoot.querySelectorAll(sel)])];

  const out = [];
  for (const [el, onTop] of hosts) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    const markers = [el.id, typeof el.className === 'string' ? el.className : '',
      el.getAttribute('data-testid') || '', el.getAttribute('aria-label') || '',
      // Alia mounts a bare fixed <div> with its app in a shadow root: no id or class to match
      window.mountAliaCustomerApp && [el, ...el.querySelectorAll('*')].some(n => n.shadowRoot) ? 'alia-app' : '',
      ...[...el.querySelectorAll('iframe')].map(f => f.src || f.id || f.name || ''),
      ...[...el.querySelectorAll('[class],[id],[data-testid]')].slice(0, 60)
        .map(n => `${n.id} ${typeof n.className === 'string' ? n.className : ''} ${n.getAttribute('data-testid') || ''}`)].join(' ');
    const vendor = (VENDORS.find(([, re]) => re.test(markers)) || [null])[0];
    const text = deepText(el).replace(/\s+/g, ' ').trim().slice(0, 400);
    const inputs = deepAll(el, 'input:not([type=hidden]),select,textarea').filter(shown);
    const hasEmail = inputs.some(i => i.type === 'email' || /email/i.test(`${i.name} ${i.placeholder} ${i.autocomplete} ${i.getAttribute('aria-label') || ''}`));
    const hasTel = inputs.some(i => i.type === 'tel' || /phone|tel/i.test(`${i.name} ${i.autocomplete}`));
    const kForm = el.matches('[data-testid^="klaviyo-form-"]') ? el : el.querySelector('[data-testid^="klaviyo-form-"]');
    const coverage = (w * h) / va;
    const isBar = (r.top <= 1 || r.bottom >= vh - 1) && h < vh * 0.22 && w > vw * 0.9;  // header / bottom nav / sticky ATC
    const cookie = !hasEmail && COOKIE.test(text) && /accept|allow|reject|decline|deny|agree|settings|preferences|ok/i.test(text);
    const kTeaser = vendor === 'klaviyo' && (/teaser/i.test(markers) || (!kForm && coverage < 0.06));

    let kind = null;
    if (cookie) kind = 'cookie_banner';
    else if (!hasEmail && !kForm && GEO.test(text)) kind = 'geo_notice';
    else if (kTeaser) kind = 'teaser';
    else if ((hasEmail || hasTel || kForm) && !(isBar && !kForm && !vendor)) kind = coverage < 0.04 ? 'teaser' : 'capture_form';
    else if (vendor && vendor !== 'klaviyo') kind = coverage < 0.04 ? 'teaser' : 'vendor_overlay';
    else if (coverage >= 0.25 && text.length >= 15 && !isBar) kind = 'other_overlay';
    if (!kind) continue;

    if (!el.dataset.paId) el.dataset.paId = String(Math.random()).slice(2, 10);
    const kId = kForm ? kForm.getAttribute('data-testid').replace('klaviyo-form-', '') : null;
    out.push({
      pa_id: el.dataset.paId, kind, vendor, klaviyo_form_id: kId,
      key: `${kind}|${vendor || ''}|${kId || text.slice(0, 50)}`,
      text, has_email: hasEmail, has_tel: hasTel, inputs: inputs.map(i => i.type || i.tagName.toLowerCase()),
      bbox: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(w), h: Math.round(h) },
      coverage_pct: Math.round(coverage * 1000) / 10,
      role: el.getAttribute('role'), aria_modal: el.getAttribute('aria-modal'), on_top: onTop,
    });
  }
  // Klaviyo embedded (inline) forms are not overlays but still count as capture points.
  const embedded = [...document.querySelectorAll('div[class*="klaviyo-form-"]')]
    .map(d => (d.className.match(/klaviyo-form-([A-Za-z0-9]{6})\b/) || [])[1])
    .filter(id => id && /[A-Z]/.test(id));  // form ids are 6 mixed-case chars; skips theme classes like klaviyo-form-image
  const doc = document.scrollingElement || document.documentElement;
  const maxScroll = Math.max(1, doc.scrollHeight - innerHeight);
  return {
    overlays: out, embedded_klaviyo_forms: [...new Set(embedded)],
    scroll_pct: Math.round(Math.min(100, (scrollY / maxScroll) * 100)),
    since_nav_start_s: Math.round(performance.now() / 100) / 10,
  };
}
