#!/usr/bin/env python3
"""
VACA Campaign 50 — Mechanical Repair Pass
==========================================
Fixes the systematic generator bug found by the static scan on ALL 50 builds:

  `import * from './x.ts';`   ← INVALID TypeScript (TS1005)
  →  `import './x.ts';`       ← valid side-effect import

The root cause is in backend/src/layers/fileGenerator.ts buildImportStatement()
(now fixed upstream). This script applies the same fix to the artifacts the
buggy generator already produced, so the builds compile under `tsc --noEmit`.

It also strips `.ts`/`.js` suffixes from relative import specifiers
(`from './x.ts'` → `from './x'`) so the projects also compile under the
generated tsconfig without needing --allowImportingTsExtensions.

Usage:
  python3 scripts/repair-campaign-50.py [--no-scan]
"""

import json, os, re, sys, subprocess

MANIFEST = "data/campaign50-manifest.json"
SCAN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan-campaign-50.py")
REPAIR_LOG = "data/campaign50-repairs.md"

# import * from './x.ts';   →   import './x.ts';
STAR_IMPORT_RE = re.compile(
    r"""^(\s*)import\s+\*\s+from\s+['"]([^'"]+)['"]\s*;""", re.M
)
# from './x.ts' | from './x.js' | import './x.ts'  →  from './x'
# Groups: G1 (from | import( | import), G2 opening quote, G3 path, G4 ext, G5 closing quote.
# The trailing whitespace is captured into G1 so the opening quote is ALWAYS G2.
EXT_SPECIFIER_RE = re.compile(
    r"""\b(from\s+|import\s*\(\s*|import\s+)(['"])(\.{1,2}/[^'"]+?)\.(ts|js|mjs|cjs)(['"])""",
    re.M,
)


def fix_imports(content: str) -> str:
    changed = content
    changed = STAR_IMPORT_RE.sub(r"\1import '\2';", changed)
    changed = EXT_SPECIFIER_RE.sub(r"\1\2\3\5", changed)
    return changed


def repair_build(b):
    """Repair one build directory. Returns (changed_files, unchanged_count)."""
    out = b.get("outputDir", "")
    if not out or not os.path.isdir(out):
        return [], 0
    changed_files = []
    unchanged = 0
    for root, _dirs, files in os.walk(out):
        for fn in files:
            if not fn.endswith((".ts", ".js")):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except Exception:
                continue
            fixed = fix_imports(src)
            if fixed != src:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(fixed)
                changed_files.append(p.replace(out, "").lstrip("/"))
            else:
                unchanged += 1
    return changed_files, unchanged


def main(do_scan=True):
    with open(MANIFEST) as f:
        manifest = json.load(f)
    builds = manifest.get("builds", [])

    total_changed = 0
    per_build = []
    for b in builds:
        if b.get("status") != "built":
            continue
        changed, unchanged = repair_build(b)
        if changed:
            total_changed += len(changed)
            per_build.append((b["name"], changed))
        print(f"  {'🔧' if changed else '✅'} {b['name']}: {len(changed)} file(s) fixed, {unchanged} clean")

    # Write the repair log
    os.makedirs(os.path.dirname(REPAIR_LOG), exist_ok=True)
    with open(REPAIR_LOG, "w") as f:
        f.write("# VACA Campaign 50 — Mechanical Repair Log\n\n")
        f.write("## Root cause\n\n")
        f.write("`import * from './x.ts'` is emitted by `buildImportStatement()` in\n")
        f.write("`backend/src/layers/fileGenerator.ts` when a dependency has no detected exports.\n")
        f.write("`import * from` is not valid TypeScript (TS1005). The generator is now fixed to\n")
        f.write("emit a side-effect import (`import './x.ts'`); this pass applies the same fix to\n")
        f.write("already-generated artifacts, and strips `.ts`/`.js` suffixes from relative import\n")
        f.write("specifiers so projects compile under the generated tsconfig.\n\n")
        f.write(f"**Total files repaired across {len(per_build)} builds: {total_changed}**\n\n")
        for name, files in per_build:
            f.write(f"### {name}\n")
            for fl in files:
                f.write(f"- `{fl}`\n")
            f.write("\n")
    print(f"\n=== Repair complete: {total_changed} files fixed across {len(per_build)} builds ===")
    print(f"    Log: {REPAIR_LOG}")

    if do_scan:
        print("\n=== Re-scanning all 50 builds (post-repair) ===")
        r = subprocess.run([sys.executable, SCAN_SCRIPT], capture_output=True, text=True)
        print(r.stdout[-3000:])
        if r.returncode != 0:
            print("SCAN STDERR:", r.stderr[-1500:])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scan", action="store_true", help="skip re-scan after repair")
    args = ap.parse_args()
    main(do_scan=not args.no_scan)
