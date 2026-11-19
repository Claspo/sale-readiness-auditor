#!/usr/bin/env python3
"""Check that this machine can run the audit: Python 3.9+, Playwright with Chromium, Pillow.

Prints OK, or the exact commands to install what is missing.

Usage:
  python doctor.py
"""
import sys

ok = True
print(f"Python {sys.version.split()[0]}", "OK" if sys.version_info >= (3, 9) else "- need 3.9 or newer")
ok &= sys.version_info >= (3, 9)
try:
    import PIL  # noqa: F401
    print("Pillow OK")
except ImportError:
    ok = False
    print("Pillow missing:  python -m pip install pillow")
try:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
        print("Playwright + Chromium OK")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"Chromium missing ({e.__class__.__name__}):  python -m playwright install chromium")
except ImportError:
    ok = False
    print("Playwright missing:  python -m pip install playwright  then  python -m playwright install chromium")
print("READY" if ok else "NOT READY")
sys.exit(0 if ok else 1)
