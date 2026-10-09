#!/usr/bin/env python3
"""
R11 3D probe — second tier: mechanical dependency repair.

The raw battery showed the model consistently wires THREE.OrbitControls
wrong (nonexistent cdnjs path, or missing script). That is a standard,
mechanical CDN footgun — this pass applies the canonical fix (load
OrbitControls.js from the jsdelivr three@0.128.0 examples path) and re-runs
the render gate, so we can separate 'scene code is sound' from 'wiring weak'.

Apps that do NOT reference OrbitControls (e.g. fireworks) are re-tested
unmodified — their failure is a genuine code bug, not wiring.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r11-3d"
ORBIT = '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>'

NAMES = ["solar-system", "chess", "maze-explorer", "terrain-viewer",
         "fireworks", "product-showcase", "bar-chart", "rubiks-cube"]


def repair(html: str) -> tuple[str, bool]:
    """Inject the canonical OrbitControls script if referenced but missing.
    Returns (new_html, changed)."""
    uses = "THREE.OrbitControls" in html
    already_ok = re.search(r'<script[^>]*three@[0-9.]+/examples/js/controls/OrbitControls\.js', html) or \
                 re.search(r'<script[^>]*OrbitControls\.js[^>]*jsdelivr', html)
    if not uses or already_ok:
        return html, False
    # drop any broken controls <script> lines (wrong cdnjs path)
    html = re.sub(
        r'<script[^>]*src="[^"]*three[^"]*[/\\]controls[/\\]OrbitControls[^"]*"[^>]*></script>',
        "", html, flags=re.I)
    # inject right after the first three.min.js include
    pat = re.compile(r'(<script[^>]*three\.min\.js[^>]*></script>)', re.I)
    m = pat.search(html)
    if not m:
        return html, False
    return pat.sub(lambda mm: mm.group(1) + "\n  " + ORBIT, html, count=1), True


def gate(path: pathlib.Path, shot: pathlib.Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "smoke-test-html.py"),
         str(path), "--probe", "window.THREE !== undefined", "--out", str(shot)],
        capture_output=True, text=True, timeout=240)
    try:
        res = json.loads(proc.stdout)  # stdout is pure JSON
    except Exception:
        res = {"error": proc.stdout[:300] + proc.stderr[:200]}
    res["pass"] = proc.returncode == 0
    return res


def main() -> None:
    results = []
    for name in NAMES:
        src = OUT / f"{name}.html"
        if not src.exists():
            results.append({"name": name, "pass": False, "error": "missing source"})
            continue
        html = src.read_text(encoding="utf-8")
        new_html, changed = repair(html)
        target = src if not changed else OUT / f"{name}-repaired.html"
        if changed:
            target.write_text(new_html, encoding="utf-8")
        res = gate(target, OUT / f"{name}-repaired-shot.png")
        res["name"] = name
        res["repaired"] = changed
        results.append(res)
        errs = res.get("pageErrors", [])[:1] + res.get("consoleErrors", [])[:1]
        print(f"{'✅' if res['pass'] else '❌'} {name} "
              f"(repaired={changed}) {errs}")

    (OUT / "results-repaired.json").write_text(json.dumps(results, indent=2))
    npass = sum(1 for r in results if r.get("pass"))
    print(f"\nREPAIRED BATTERY: {npass}/{len(results)} PASS")


if __name__ == "__main__":
    main()
