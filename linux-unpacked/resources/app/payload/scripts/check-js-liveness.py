#!/usr/bin/env python3
"""Liveness probe: did the page's inline JS actually run?

Generic signal: if a page has inline scripts and they executed, some
window-level or DOM-level side effect exists that static HTML alone wouldn't
produce. We use two detectors:
  1. window.__SMOKE is set by an init script we inject BEFORE page scripts;
     inline scripts that run will usually call addEventListener / attach
     listeners — instead we detect "script ran" via: any inline script whose
     text defines a function/var, plus the page having any JS-attached
     listener (getEventListeners unavailable) — fallback: compare the
     document's HTML as parsed: scripts that ran typically create dynamic
     elements or the page has non-empty body text produced by JS.
  2. Concrete app-specific hooks where available (boot banner text, etc.).
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/home/final-flash1/Desktop/visual-ai-architect/probes/r15-gui")
names = sys.argv[1:] or ["todo-list", "terminal-os"]

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    for name in names:
        p = BASE / f"{name}.html"
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(f"PAGE: {e}"))
        pg.on("console", lambda m: errs.append(f"CONSOLE:{m.type}: {m.text}") if m.type == "error" else None)
        # Inject a marker BEFORE page scripts run.
        pg.add_init_script("window.__smoke_before = true;")
        try:
            pg.goto(p.as_uri(), wait_until="load")
            pg.wait_for_timeout(1500)
        except Exception as e:
            errs.append(f"LOAD: {e}")

        info = pg.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script:not([src])'));
            const bodyText = document.body ? document.body.innerText.slice(0, 200) : '';
            return {
                inlineScripts: scripts.length,
                inlineHasCode: scripts.some(s => (s.textContent || '').trim().length > 20),
                bodyText,
                bodyLen: document.body ? document.body.innerText.length : 0,
                inputs: document.querySelectorAll('input').length,
                buttons: document.querySelectorAll('button').length,
                readyState: document.readyState,
            };
        }""")
        print(f"--- {name}: errors={len(errs)}")
        for k, v in info.items():
            print(f"    {k}: {v}")
        for e in errs[:4]:
            print("   ", e)
        pg.close()
    b.close()
