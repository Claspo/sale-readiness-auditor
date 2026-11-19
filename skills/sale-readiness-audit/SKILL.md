---
name: sale-readiness-audit
description: >-
  Audit an online store's readiness for a seasonal sale (Black Friday, Cyber Monday, holiday, any
  peak season) from its URL. A browser walks the store like shoppers do, on desktop and mobile: first
  visit, landing from an ad on a product, browsing and leaving, leaving with a full cart, coming back,
  cart and checkout. The audit checks the sale message, product pages, cart, checkout, email/SMS
  signup forms (where they appear, offer, targeting, triggering, mobile fit), an optional test signup,
  language versions, trust and speed, and returns an HTML report with what was seen, why it matters and
  what to fix. Use for "audit my store for Black Friday", "is my site ready for the sale", "BFCM
  audit", "peak season audit", "check my popups before Black Friday", "аудит сайту до розпродажу".
---

# Sale readiness audit

You run a store audit for the person in front of you, from a URL they give. Scripts collect evidence;
you judge what needs eyes, write the findings, and render the report. Everything runs on this machine;
nothing is sent anywhere.

The scripts live in `scripts/` next to this file (Claude Code shows this skill's base directory when it
loads; use that absolute path below as `<skill>`). Call Python as `python3` on macOS/Linux and `python`
on Windows. The checklist with every check's what / how / how-to-read is `<skill>/checklist.json`: read
its `rules` and `statuses` before judging.

## 1. Ask once, then work

Before anything runs, ask in one message (skip what the person already said):

1. The store URL.
2. The report language (default: the language they write to you in).
3. Test signup: "May I sign up on the store's form with your email to check the thank-you step, the
   welcome email and the code? Only on your own store, or one you have permission to test." Default
   **no**. With yes, take the email address they give; never invent one, never use a phone number.

Then run without further questions.

## 2. Check the machine

```bash
python3 <skill>/scripts/doctor.py
```

On NOT READY, run the install commands it prints (they install Playwright, Chromium and Pillow into the
user's Python) after telling the person what you are installing, then run doctor again.

## 3. Walk the store (6-9 minutes)

Output folder: `./sale-readiness-audit/<domain>/<YYYY-MM-DD>/` under the current working directory.

```bash
python3 <skill>/scripts/walk.py <url> --out ./sale-readiness-audit/<domain>/<date>
```

Run it in the background and tell the person it takes several minutes. When it ends, read the warnings
it prints. A bot check, a password page or a geo redirect on the homepage stops the audit: say so, and
offer `--headed` (a visible browser often passes).

The walk uses this machine's internet connection, so pop-ups targeted at other countries may not show.
Say this in the report's evidence wherever it matters (block E), never as a finding.

## 4. Test signup (only with a yes in step 1)

```bash
python3 <skill>/scripts/signup_test.py --out <folder> --email <their email>
```

If it shows a code, check it in the cart (Shopify stores):

```bash
python3 <skill>/scripts/signup_test.py --out <folder> --code <CODE>
```

Welcome email (check J3): if you have a mail connector for the person's inbox, search it for the store's
email from the last 30 minutes and record whether it arrived, how many minutes after the signup, and
whether it holds the code. Otherwise ask the person to check and tell you; until then J3 stays
`cannot_verify`.

## 5. Measured verdicts

```bash
python3 <skill>/scripts/prejudge.py --out <folder>
```

It writes `draft.json`: checks marked `auto` already carry a status and evidence; `visual` checks carry
`screenshots_to_view` and `facts`, with no status.

## 6. Judge and write

Copy `draft.json` to `verdicts.json` and complete every item:

- **Visual checks**: open each screenshot in `screenshots_to_view` (they are in `<folder>/shots/`) and
  read `facts`. Set `status`, `evidence` (what you saw, with the store's own words in quotes and the
  device), and `screenshots` (the files that show it). Follow the item's `read` line in checklist.json.
- **Auto checks**: open the screenshot of every signup form they cite. If the detector mistook something
  (a cart drawer, a size guide, a chat widget counted as a form), correct the status and say why in the
  evidence. Keep their numbers otherwise.
- **Every `missing` or `partial`**: add `why_it_matters` (one or two sentences about this store; start
  from the item's `why` in checklist.json) and `recommendation` (a concrete change: what, where, with
  which words or numbers taken from the store's own offer).
- Write `evidence`, `why_it_matters` and `recommendation` in the report language.

Rules you never break (from checklist.json `rules`):

- A pop-up with a signup form and one without a form are separate: never count an announcement pop-up
  as a capture point.
- A pop-up covering the screen or the product page is not a finding: that is what pop-ups are for.
- `missing` only for something the walk would have seen on a page it reached; otherwise `cannot_verify`
  with what would be needed.
- No invented numbers, no fake urgency: a timer, stock count or "X people viewing" is recommended only
  as "tied to real data".
- Facts first: no "great job" and no scores beyond the counts the report shows.

## 7. Render and hand over

```bash
python3 <skill>/scripts/render.py --out <folder> --lang <en|uk>
```

Open `report.html` for the person (macOS `open`, Windows `start`, Linux `xdg-open`). In your reply give:
the count line (passes of checks that apply), the five fixes that matter most for the sale (missing
before partial; capture points, the offer and the cart before cosmetic items), and the path to the
report. The report is one self-contained HTML file they can send to their team or agency.
