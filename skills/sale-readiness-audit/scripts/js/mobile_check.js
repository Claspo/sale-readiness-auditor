// Mobile fit of a popup found by detect.js (by its data-pa-id), measured on what is rendered:
// does the content fit the screen, is the close button big enough, is the input font >= 16 px
// (smaller makes iOS zoom the page on focus), is the main button visible without scrolling.
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`);
  if (!host) return null;
  const vw = innerWidth, vh = innerHeight;
  const shown = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.05; };
  const box = el => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
  const inputs = [...host.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea')].filter(shown);
  const closeSel = 'button[aria-label*="close" i], button[aria-label*="dismiss" i], .klaviyo-close-form, [class*="close" i]:is(button,a,div,span,svg)';
  const close = [...host.querySelectorAll(closeSel)].filter(shown).sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width)[0] || null;
  const buttons = [...host.querySelectorAll('button, [role=button], input[type=submit]')].filter(e => shown(e) && e !== close && !(close && close.contains(e)));
  const main = buttons.sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height)[0] || null;
  // content = everything a visitor reads or taps, so the dimmed backdrop does not count as the card
  const parts = [...inputs, ...buttons, ...[...host.querySelectorAll('p, h1, h2, h3, h4, span, img')].filter(e => shown(e) && (e.innerText || e.tagName === 'IMG'))];
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  for (const e of parts) { const q = e.getBoundingClientRect(); l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom); }
  const content = parts.length ? { x: Math.round(l), y: Math.round(t), w: Math.round(r - l), h: Math.round(b - t) } : null;
  const fonts = inputs.map(i => parseFloat(getComputedStyle(i).fontSize));
  const cb = close && close.getBoundingClientRect();
  const mb = main && main.getBoundingClientRect();
  return {
    viewport: { w: vw, h: vh },
    content_box: content,
    content_fits_screen: content ? (l >= -1 && r <= vw + 1 && t >= -1 && b <= vh + 1) : null,
    content_wider_than_screen: content ? (l < -1 || r > vw + 1) : null,
    close_button: close ? { box: box(close), size_ok: cb.width >= 24 && cb.height >= 24, on_screen: cb.left >= 0 && cb.right <= vw && cb.top >= 0 && cb.bottom <= vh } : null,
    input_font_px: fonts.length ? Math.min(...fonts) : null,
    input_font_ok: fonts.length ? Math.min(...fonts) >= 16 : null,
    main_button: main ? { text: (main.innerText || main.value || '').trim().slice(0, 40), box: box(main), visible_without_scroll: mb.top >= 0 && mb.bottom <= vh } : null,
  };
}
