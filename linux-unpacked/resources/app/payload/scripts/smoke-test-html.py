#!/usr/bin/env python3
"""
Render smoke-test for generated HTML apps (3D gate + behavioral gate).

Opens an HTML file in headless Chrome (via Playwright + the system Chrome
binary), waits for it to settle, and reports:

  - console errors / page errors (CDN failures, undefined THREE, exceptions)
  - whether a WebGL <canvas> was created (three.js renders into one)
  - whether the page's 3D-fallback banner is visible (CDN blocked/offline)
  - an app-specific probe expression, if given
  - a screenshot for human inspection

With --behavioral (the interactive-app gate) it ALSO performs primary
interactions on the page — fills the first text input and presses Enter,
clicks the primary control, clicks a second control — then reports any NEW
console/page errors those interactions triggered. A page that loads clean but
crashes when the user actually clicks is a behavioral failure (the exact
"compiles but doesn't work" class). Also reports whether the page rendered any
content at all (blank-page detection).

Exit code 0 = PASS, 1 = FAIL.
  - default mode: any console/page error, missing WebGL canvas (3D), or fallback
  - behavioral mode: any console/page error, NEW errors after interactions, or
    a blank page (canvas NOT required — 2D apps are the target)

Usage:
    python3 scripts/smoke-test-html.py <file.html> [--behavioral] [--probe 'window.THREE !== undefined'] [--wait 6000] [--out /tmp/shot.png]
"""

import argparse
import json
import os
import sys

CHROME = "/usr/bin/google-chrome"

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="Path to the HTML file to test")
    ap.add_argument("--behavioral", action="store_true",
                    help="Run primary-interaction checks and fail on NEW errors they trigger")
    ap.add_argument("--probe", default=None,
                    help="JS expression that must evaluate truthy (e.g. 'window.THREE !== undefined')")
    ap.add_argument("--wait", type=int, default=6000, help="Settle wait in ms (default 6000)")
    ap.add_argument("--out", default=None, help="Screenshot output path (default: next to input, -shot.png)")
    args = ap.parse_args()

    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(json.dumps({"pass": False, "error": f"file not found: {path}"}))
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"pass": False, "error": "playwright not installed (pip install playwright)"}))
        sys.exit(1)

    console_errors = []
    page_errors = []
    probes = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=CHROME, headless=True,
                                        args=["--no-sandbox", "--disable-gpu-sandbox", "--use-gl=swiftshader",
                                              "--enable-unsafe-swiftshader"])
        except Exception as e:
            print(json.dumps({"pass": False, "error": f"chrome launch failed: {e}"}))
            sys.exit(1)

        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda msg: console_errors.append(msg.text)
                if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        try:
            page.goto("file://" + path, wait_until="load", timeout=20000)
        except Exception as e:
            page_errors.append(f"navigation failed: {e}")

        page.wait_for_timeout(args.wait)

        # Canvas/WebGL detection
        canvas = page.evaluate("""() => {
            const c = document.querySelector('canvas');
            if (!c) return { found: false };
            try {
                const gl = c.getContext('webgl2') || c.getContext('webgl');
                return { found: true, webgl: !!gl };
            } catch (e) {
                return { found: true, webgl: false, err: String(e) };
            }
        }""")

        # Fallback banner visible?
        fallback_visible = page.evaluate("""() => {
            const f = document.getElementById('fallback');
            if (!f) return false;
            const st = getComputedStyle(f);
            return st.display !== 'none';
        }""")

        if args.probe:
            try:
                probes[args.probe] = bool(page.evaluate(args.probe))
            except Exception as e:
                probes[args.probe] = f"eval error: {e}"

        # ── Behavioral interactions (only in --behavioral mode) ──
        interactions = []
        interaction_errors = []
        body_text_len = 0
        if args.behavioral:
            # Snapshot the error lists BEFORE interacting so we can report only
            # the errors the interactions THEMSELVES triggered (a clean-load-
            # but-crashes-on-click app is the exact behavioral failure class).
            base_console = list(console_errors)
            base_page = list(page_errors)

            def record_interaction(label):
                # Errors are attributed to the interaction that FIRST produced
                # them by slicing against the snapshot taken before it ran.
                new_c = [e for e in console_errors if e not in base_console
                         and "favicon" not in e.lower()]
                new_p = [e for e in page_errors if e not in base_page]
                interactions.append(label)
                if new_c or new_p:
                    interaction_errors.append(
                        f"{label} triggered: " + "; ".join(new_c + new_p)[:300])
                # Advance the snapshot so the NEXT interaction only reports its
                # own new errors (no double-reporting across interactions).
                base_console[:] = list(console_errors)
                base_page[:] = list(page_errors)

            # 1) Fill the first visible text-ish input and press Enter — the
            #    single most common primary interaction in generated apps
            #    (todo add, search, chat send). Skip file/checkbox/radio/hidden.
            try:
                text_input = page.query_selector(
                    "input:not([type]), input[type=text], input[type=search], "
                    "input[type=number], textarea")
                if text_input and text_input.is_visible():
                    text_input.fill("test value")
                    text_input.press("Enter")
                    page.wait_for_timeout(400)
                    record_interaction("filled first text input + Enter")
                else:
                    interactions.append("no visible text input found")
            except Exception as e:
                interaction_errors.append(f"text-input interaction failed: {e}")

            # 2) Click the primary control (first visible button-ish element).
            try:
                primary = page.query_selector(
                    "button, [role=button], input[type=submit], input[type=button]")
                if primary and primary.is_visible():
                    primary.click()
                    page.wait_for_timeout(400)
                    record_interaction("clicked primary control")
                else:
                    # No real button: try the first link as the primary action.
                    link = page.query_selector("a[href]")
                    if link and link.is_visible():
                        link.click()
                        page.wait_for_timeout(400)
                        record_interaction("clicked first link")
                    else:
                        interactions.append("no visible control found")
            except Exception as e:
                interaction_errors.append(f"primary-click failed: {e}")

            # 3) Click a SECOND control (secondary action — toggle, clear, etc.).
            try:
                controls = page.query_selector_all(
                    "button, [role=button], input[type=submit], input[type=button], "
                    "input[type=checkbox], input[type=radio]")
                visible = [c for c in controls if c.is_visible()]
                if len(visible) > 1:
                    visible[1].click()
                    page.wait_for_timeout(400)
                    record_interaction("clicked secondary control")
            except Exception as e:
                interaction_errors.append(f"secondary-click failed: {e}")

            # Blank-page detection: a generated app that renders NOTHING (no
            # text, no canvas, no controls) is a behavioral failure — the
            # "empty page" class. Canvas apps legitimately have no body text.
            body_text_len = page.evaluate(
                "() => (document.body && document.body.innerText || '').trim().length")

        out = args.out or (path.rsplit(".", 1)[0] + "-shot.png")
        try:
            page.screenshot(path=out, full_page=False)
        except Exception as e:
            out = f"screenshot failed: {e}"

        browser.close()

    # ── Verdict ──
    bad_console = [e for e in console_errors
                   if "favicon" not in e.lower() and "ERR_CERT" not in e]
    # Is this a 3D/graphics app? Its canvas + fallback-banner checks stay
    # REQUIRED even in behavioral mode — a 3D app with a blocked CDN or a
    # missing WebGL canvas is still a failure even if nothing crashes.
    try:
        import re as _re
        with open(path, "r", errors="replace") as fh:
            html_src = fh.read(200000)
        # Mirrors the TS-side gate (codePlanner.ts runRenderSmoke): word-
        # bounded "three" (so a 2D app that merely says "three" isn't
        # misdetected as 3D), webgl, or a webgl getContext call.
        # Mirrors the TS-side gate (codePlanner.ts runRenderSmoke): the three.js
        # OBJECT/library pattern (new THREE.X / THREE.X / three.js / from
        # 'three'), webgl, or a webgl getContext call — NOT the bare word
        # "three", so a 2D app that merely says "three" isn't misdetected as 3D.
        is_3d = bool(_re.search(
            r"new\s+THREE\.|THREE\.[A-Z]|three(?:\.min)?\.js|from\s+['\"]three['\"]"
            r"|webgl|getContext\s*\(\s*['\"]webgl", html_src, _re.I))
    except Exception:
        is_3d = False
    if args.behavioral:
        # 2D interactive apps do NOT require a WebGL canvas — only absence of
        # errors, no NEW errors from interactions, and some rendered content.
        blank = body_text_len == 0 and not canvas.get("found")
        failed = (bool(page_errors) or bool(bad_console)
                  or bool(interaction_errors) or blank
                  or (is_3d and (fallback_visible or not canvas.get("found"))))
    else:
        failed = (bool(page_errors) or bool(bad_console)
                  or fallback_visible or not canvas.get("found"))
    if args.probe and args.probe in probes and probes[args.probe] is False:
        failed = True

    result = {
        "pass": not failed,
        "file": os.path.basename(path),
        "consoleErrors": bad_console[:10],
        "pageErrors": page_errors[:10],
        "canvas": canvas,
        "fallbackVisible": fallback_visible,
        "probes": probes,
        "behavioral": {
            "interactions": interactions,
            "interactionErrors": interaction_errors[:10],
            "bodyTextLength": body_text_len,
        } if args.behavioral else None,
        "screenshot": out if not str(out).startswith("screenshot failed") else None,
    }
    print(json.dumps(result, indent=1))
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
