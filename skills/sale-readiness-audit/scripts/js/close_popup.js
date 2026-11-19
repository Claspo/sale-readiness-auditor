// Closes an overlay found by detect.js (by its data-pa-id) the way a visitor would: X / close / "no thanks".
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`);
  if (!host) return null;
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const sel = 'button[aria-label*="close" i], button[aria-label*="dismiss" i], .klaviyo-close-form, [class*="close" i]:is(button,a,div,span,svg)';
  const b = [...host.querySelectorAll(sel)].find(visible)
    || [...host.querySelectorAll('button, a, [role=button]')].find(e => visible(e) && /^(×|✕|x|no,? thanks.*|close|maybe later|not now)$/i.test((e.innerText || '').trim()));
  if (b) { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); return { method: 'button', text: (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 40) }; }
  // country / language pickers have no X: a visitor confirms the pre-selected country
  const cta = [...host.querySelectorAll('button, a, [role=button], input[type=submit]')].find(e => visible(e) &&
    /^(continue|shop now|stay|confirm|ok|go|save|compre agora|comprar|continuar|weiter|continuer)\.?$/i.test((e.innerText || e.value || '').trim()));
  if (cta) { cta.click(); return { method: 'primary_cta', text: (cta.innerText || cta.value || '').trim().slice(0, 40) }; }
  return null;
}
