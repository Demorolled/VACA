#!/usr/bin/env python3
"""
repair-3d-wiring.py — mechanical Three.js wiring repair (R11/R13 lesson).

The R11 and R13 probes both showed the model's dominant 3D failure mode is
DEPENDENCY WIRING, not scene-building:

  1. `THREE.OrbitControls is not a constructor` — the app calls the
     constructor but never loads the OrbitControls addon script
     (https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js)
     after the core three.min.js script.
  2. CDN path case-sensitivity — `r128/Three.js` (capital T) 404s; the real
     file is `r128/three.min.js`.

This module applies the minimal, safe repairs to a generated HTML file:

  * if the app uses THREE.OrbitControls but no addon script is loaded,
    inject the addon <script> right after the core three.min.js tag;
  * if a <script src> contains `three.js/r128/Three.js` (capital T core),
    lowercase it to `three.min.js`;
  * if the app uses REMOVED r128 APIs, alias them to their replacements:
    THREE.CubeGeometry -> THREE.BoxGeometry (same constructor args).

It returns the repaired text. Callers (the R14 data builder and the R14
probe) use it BEFORE the render gate so "wiring" failures can be separated
from real "breadth" failures in the measurement.

CLI:  python3 scripts/repair-3d-wiring.py <in.html> [--out <out.html>]
      (prints the repaired HTML to stdout if --out is omitted)
"""
import re
import sys
from pathlib import Path

CORE_CDN = r"https://cdnjs\.cloudflare\.com/ajax/libs/three\.js/r128/three\.min\.js"
ADDON_CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"
ADDON_TAG = f'<script src="{ADDON_CDN}"></script>'

# Matches a <script src="...three.min.js"></script> tag (any quote style).
SCRIPT_TAG_RE = re.compile(
    r"<script[^>]*src=['\"][^'\"]*three\.min\.js['\"][^>]*>\s*</script>",
    re.IGNORECASE,
)
# Capital-T core path (the 404 bug): .../three.js/r128/Three.js  (not the addon).
CAPT_T_RE = re.compile(r"(three\.js/r128/)Three\.js", re.IGNORECASE)
# Removed-API aliases (constructor-compatible in r128).
REMOVED_APIS = [
    ("THREE.CubeGeometry", "THREE.BoxGeometry"),  # removed long ago; r128 name is BoxGeometry
]


def repair_wiring(html: str) -> str:
    """Apply the mechanical wiring repairs. Returns the repaired HTML."""
    fixes = []

    for old, new in REMOVED_APIS:
        if old in html:
            html = html.replace(old, new)
            fixes.append(f"aliased removed API {old} -> {new}")

    uses_orbit = "THREE.OrbitControls" in html or "OrbitControls(" in html
    has_addon = "OrbitControls.js" in html
    if uses_orbit and not has_addon:
        m = SCRIPT_TAG_RE.search(html)
        if m:
            html = html[: m.end()] + "\n" + ADDON_TAG + html[m.end():]
            fixes.append("injected OrbitControls addon script after three.min.js")
        else:
            fixes.append("⚠️  OrbitControls used but no three.min.js tag found to anchor")
    else:
        fixes.append("no OrbitControls addon needed" if not uses_orbit else "addon script already present")

    if CAPT_T_RE.search(html):
        html = CAPT_T_RE.sub(r"\1three.min.js", html)
        fixes.append("lowercased capital-T Three.js CDN path")

    return html, fixes


def main() -> None:
    src = Path(sys.argv[1])
    html = src.read_text(encoding="utf-8", errors="replace")
    repaired, fixes = repair_wiring(html)
    out = None
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    if out:
        out.write_text(repaired, encoding="utf-8")
        print(f"[repair-3d-wiring] {src.name}: {'; '.join(fixes)}")
        print(f"[repair-3d-wiring] wrote {out}")
    else:
        sys.stdout.write(repaired)


if __name__ == "__main__":
    main()
