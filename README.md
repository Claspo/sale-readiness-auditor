# Sale Readiness Audit — a Claude Code plugin by Claspo

Give Claude a store URL; get an audit of how ready the store is for Black Friday, Cyber Monday or any
seasonal sale, as one HTML report you can send to your team or agency.

A browser walks the store the way shoppers do, on desktop and on a phone: a first visit, a visitor
landing from an ad on a product page, someone browsing three products and leaving, someone leaving with
a full cart, a returning visitor, the cart and the checkout (opened, never filled). The audit then checks
about 50 things that move sales in a peak week:

- **The sale on the site** — announced in the first screen, a concrete offer, a real end date, one click
  from the menu, free-shipping threshold, delivery cutoff.
- **Products, cart, checkout** — saving shown at every step, reviews near the price, delivery and returns
  at the buy button, express wallets, guest checkout.
- **Email and SMS signup forms** — whether a form appears for each of those visitors, whether the exit
  offer differs from the welcome offer, what returning visitors and subscribers see, whether the form
  offers less than the sale already on the site, teaser after close, overlap with the cookie banner, how
  the form fits a phone and whether the keyboard hides the field.
- **Optional test signup** with your own email — thank-you step, consent text, the welcome email, and
  whether the code works in the cart.
- **Language versions, trust, speed.**

Each finding comes with what was seen (screenshot), why it matters and what to change.

## Install

In Claude Code:

```
/plugin marketplace add Claspo/sale-readiness-auditor
/plugin install sale-readiness-audit@claspo
```

It needs Python 3.9+ on your machine. On first use Claude checks for Playwright, Chromium and Pillow and
offers to install them (`pip install playwright pillow`, `playwright install chromium`).

## Use

```
/sale-readiness-audit https://your-store.com
```

or just ask: "audit my store for Black Friday: your-store.com". Claude asks for the report language and
whether you allow a test signup, then runs for about 10 minutes. The report lands in
`./sale-readiness-audit/<domain>/<date>/report.html`.

## What it does not do

- It submits nothing except, if you allow it, one email signup with your own address. The cart gets one
  product; the checkout is only opened.
- It browses from your own internet connection, so pop-ups targeted at other countries may not show.
- Speed is one lab measurement on your connection: a hint, not a Core Web Vitals report.
- It audits what a visitor can see. Your pop-up app's settings, A/B tests and analytics are out of view.

## Privacy

Everything runs on your machine. Screenshots and results stay in the output folder; nothing is sent to
Claspo.

---

Made by [Claspo](https://claspo.io) — AI-managed pop-ups and email capture for e-commerce.
