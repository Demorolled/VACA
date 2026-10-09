#!/usr/bin/env python3
"""How does Chrome treat an unclosed <script>? Does the JS run? Any errors?"""
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

CASE_A = """<!DOCTYPE html><html><body>
<script>
window.HIT = 'A-SET';
function greet() { return 'hi'; }
</body>
</html>"""

CASE_B = """<!DOCTYPE html><html><body>
<script>
window.HIT = 'B-SET';
</script>  <!-- this is a script element with no src, but closed -->
<script src="https://cdn.example.com/foo.js"></script>
</body>
</html>"""

# mimic the repaired shape: wrap + no closing </script>, trailing </body></html>
CASE_C = """<!DOCTYPE html><html><body>
<div id="app"></div>
<script>
document.addEventListener('DOMContentLoaded', () => {
const el = document.getElementById('app');
el.textContent = 'RAN';
});
</body>
</html>"""

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    for name, html in [("A-simple-unclosed-EOF", CASE_A), ("B-closed-then-src", CASE_B), ("C-repaired-shape", CASE_C)]:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            path = Path(f.name)
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(f"PAGE: {e}"))
        pg.on("console", lambda m: errs.append(f"CONSOLE:{m.type}: {m.text}") if m.type == "error" else None)
        try:
            pg.goto(path.as_uri(), wait_until="load")
            pg.wait_for_timeout(800)
            hit = pg.evaluate("window.HIT || 'NOT-SET'")
            app_txt = pg.evaluate("(document.getElementById('app')||{}).textContent || 'NO-EL'")
        except Exception as e:
            hit, app_txt = f"EVAL-ERR: {e}", ""
        print(f"--- {name}")
        print(f"    errors: {errs}")
        print(f"    window.HIT = {hit} | #app text = {app_txt}")
        pg.close()
        path.unlink(missing_ok=True)
    b.close()
