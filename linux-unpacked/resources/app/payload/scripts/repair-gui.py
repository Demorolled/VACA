#!/usr/bin/env python3
"""
repair-gui.py — mechanical GUI-app repair (R15 lesson).

The R15 GUI battery measures 2D DOM apps (dashboards, kanban, chat, ...)
with a DOM bar, not a WebGL bar. The defect classes seen in prior GUI
generations are different from the 3D wiring classes:

  1. Script/init-order: handlers and render calls run before the DOM is
     parsed (elements are null) -> wrap init in DOMContentLoaded when the
     app references document.getElementById in a bare top-level call.
  2. Null-safe handler wiring: `btn.onclick = doThing` where doThing reads
     a missing element -> guard the handler body.
  3. Common 2D gotchas: <script> placed in <head> without defer while the
     body is referenced, `document.querySelector(...).addEventListener`
     on a possibly-missing node.

This module applies minimal, SAFE mechanical repairs and prints the
repaired HTML. It is deliberately conservative: it only fixes classes that
are unambiguous string patterns, and it never changes behavior it cannot
prove.

CLI:  python3 scripts/repair-gui.py <in.html> [--out <out.html>]
      (prints the repaired HTML to stdout if --out is omitted)
"""
import re
import sys
from pathlib import Path

# ─── Script-position / DOM-ready guard ──────────────────────────────────────
# If there is any <script> that (a) is not type=module, (b) has no
# defer/async, and (c) the page has a <body> that appears AFTER it, and the
# script references getElementById at top level — the app risks null refs.
# Safe fix: wrap the app script's execution in a DOMContentLoaded listener.
TOPLEVEL_GETELEM = re.compile(r"getElementById\s*\(")
# IDs referenced inside a script via getElementById('X').
REF_IDS = re.compile(r"getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def _wrap_needed(html: str, script_end: int, body: str) -> bool:
    """True only when the wrap is positionally REQUIRED: at least one element
    the script queries is DEFINED AFTER the script element in the HTML.

    `script_end` is the index just past the script's closing </script>, so the
    scanned tail EXCLUDES the script body itself — otherwise an id appearing
    inside a JS string/template literal (e.g. innerHTML = '<div id="app">',
    exactly the code-editor/markdown-previewer class) would false-positive and
    reintroduce the global-scope regression.

    If every referenced element appears before the script (the common
    "script at end of body" layout), the top-level getElementById calls are
    already safe at parse time — wrapping would be pure harm: it moves
    function declarations out of the global scope, breaking inline
    onclick="fn()" handlers (R15 code-editor regression: "run is not
    defined").
    """
    ids = REF_IDS.findall(body)
    if not ids:
        return False
    tail = html[script_end:]
    # Attribute-boundary check: (?<![\w-])id= avoids matching data-id="X" /
    # myid="X" substrings (\bid= is NOT enough — the hyphen in data-id is a
    # word/non-word boundary itself).
    return any(
        re.search(rf"(?<![\w-])id=[\"']{re.escape(i)}[\"']", tail)
        for i in ids
    )


def _wrap_in_domready(js_body: str) -> str:
    stripped = js_body.strip()
    if not stripped:
        return js_body
    return (
        "document.addEventListener('DOMContentLoaded', () => {\n"
        + stripped
        + "\n});\n"
    )


def repair_gui(html: str) -> str:
    """Apply mechanical GUI repairs. Returns the repaired HTML."""
    fixes = []

    # 1) Remove any leading '<html ...>' junk if extract accidentally kept
    #    markup above DOCTYPE (models sometimes emit <html> first).
    m = re.match(r"^\s*<html[^>]*>", html)
    if m and "<!DOCTYPE" not in html[: m.end()].lower():
        # keep it simple: only strip a stray bare '<html>' prefix
        html = html[m.end():]
        fixes.append("stripped stray <html> prefix")

    # 2) DOMContentLoaded guard for inline top-level scripts that touch the
    #    DOM. Only applies to inline scripts (no src), not already wrapped.
    def guard_inline(match):
        tag, body = match.group(1), match.group(2)
        # Already self-guarding (DOMContentLoaded or onload anywhere) → leave
        # it alone. Conservative: a substring check beats a first-line check
        # (a comment/helper before window.onload would otherwise double-wrap).
        if "DOMContentLoaded" in body or "window.onload" in body:
            return match.group(0)
        if TOPLEVEL_GETELEM.search(body) and _wrap_needed(html, match.end(0), body):
            fixes.append("wrapped inline script in DOMContentLoaded (element after script)")
            # CRITICAL: the regex above consumed the trailing </script> as
            # part of the match — we MUST re-emit it. Dropping it leaves an
            # unclosed <script>, which Chrome treats as dead JS at EOF (0
            # errors, but the code never runs) or "Unexpected token '<'" when
            # another <script src> follows. This bug silently made repaired
            # apps into static shells (R15 probe false-passed 10/12).
            return tag + "\n" + _wrap_in_domready(body) + "\n</script>"
        return match.group(0)

    html = re.sub(
        r"(<script(?![^>]*\bsrc=)[^>]*>)(.*?)</script>",
        guard_inline, html, flags=re.S | re.IGNORECASE)

    # 3) Null-safe: document.getElementById('X').addEventListener(...) is the
    #    single most common 2D crash (querying a missing id -> TypeError).
    #    Rewrite with optional chaining (Chrome supports it; minimal diff):
    #      document.getElementById('X')?.addEventListener(...)
    html, n1 = re.subn(
        r"document\.getElementById\((['\"][^'\"]+['\"])\)\.addEventListener\(",
        r"document.getElementById(\1)?.addEventListener(", html,
    )
    if n1:
        fixes.append(f"null-guarded getElementById(...).addEventListener x{n1}")

    # 4) querySelector(...).addEventListener -> same optional-chaining guard.
    html, n2 = re.subn(
        r"document\.querySelector\((['\"][^'\"]+['\"])\)\.addEventListener\(",
        r"document.querySelector(\1)?.addEventListener(", html,
    )
    if n2:
        fixes.append(f"null-guarded querySelector(...).addEventListener x{n2}")

    # 5) Console-only cleanup: strip `debugger;` statements (they freeze the
    #    page and the gate would time out).
    if "debugger;" in html:
        html = html.replace("debugger;", "")
        fixes.append("stripped debugger; statements")

    print("repair-gui fixes:", fixes if fixes else "none", file=sys.stderr)
    return html


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    inp = Path(sys.argv[1])
    html = inp.read_text(encoding="utf-8")
    out = repair_gui(html)
    if "--out" in sys.argv:
        o = Path(sys.argv[sys.argv.index("--out") + 1])
        o.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
