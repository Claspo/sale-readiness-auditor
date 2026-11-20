// Closes an overlay found by detect.js (by its data-pa-id) the way a visitor would: X / close / "no thanks".
(paId) => {
  const host = document.querySelector(`[data-pa-id="${paId}"]`);
  if (!host) return null;
  // fields and buttons of web-component pop-ups (Claspo) sit several shadow roots deep
  const deep = sel => { const roots = [host];
    for (let i = 0; i < roots.length && roots.length < 400; i++) { const r = roots[i]; if (r.shadowRoot) roots.push(r.shadowRoot);
      for (const n of r.querySelectorAll('*')) if (n.shadowRoot) roots.push(n.shadowRoot); }
    return roots.flatMap(r => [...r.querySelectorAll(sel)]); };
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const sel = 'button[aria-label*="close" i], button[aria-label*="dismiss" i], .klaviyo-close-form, [class*="close" i]:is(button,a,div,span,svg)';
  const b = deep(sel).find(visible)
    || deep('button, a, [role=button]').find(e => visible(e) && /^(×|✕|x|no,? thanks.*|close|maybe later|not now)$/i.test((e.innerText || '').trim()));
  if (b) { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); return { method: 'button', text: (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 40) }; }
  // country / language pickers have no X: a visitor confirms the pre-selected country
  const cta = deep('button, a, [role=button], input[type=submit]').find(e => visible(e) &&
    /^(continue|shop now|stay|confirm|ok|go|save|compre agora|comprar|continuar|weiter|continuer)\.?$/i.test((e.innerText || e.value || '').trim()));
  if (cta) { cta.click(); return { method: 'primary_cta', text: (cta.innerText || cta.value || '').trim().slice(0, 40) }; }
  return null;
}
