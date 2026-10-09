#!/usr/bin/env python3
"""
VACA Campaign 50 — Static Scan & Wiki Generator
================================================
Reads data/campaign50-manifest.json, scans every built project directory,
classifies each build PASS/FAIL, and emits:
  - data/campaign50-scan.json      — per-build scan results
  - data/campaign-wiki/<slug>.md   — wiki page per build (passes: documentation;
                                     failures: root cause + fix + lesson)
  - data/campaign50-report.md      — campaign summary report

Checks per build (static, no browser):
  1. index.html exists & non-trivial size
  2. HTML structure parses (doctype/html/body, balanced script tags)
  3. Source compiles via `tsc --noEmit --allowImportingTsExtensions` (project tsconfig)
  4. No placeholder stubs (not implemented / placeholder for / lorem / etc.)
  5. Non-empty source files (no zero-byte generated files)
  6. Security: source scan for REAL critical patterns (eval / Function ctor /
     child_process / SQL string concat); innerHTML & cookies are advisory only

Usage:
  python3 scripts/scan-campaign-50.py [--wiki-only]
"""

import json, os, sys, re, subprocess
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser

MANIFEST = "data/campaign50-manifest.json"
SCAN_OUT = "data/campaign50-scan.json"
WIKI_DIR = "data/campaign-wiki"
REPORT = "data/campaign50-report.md"

# Strong failure signals only. TODO/FIXME are excluded — generated code commonly
# carries informational TODO comments (the fileGenerator prompt encourages comments),
# and false failures would waste repair effort and pollute the training signal.
# Bare \bplaceholder\b is NOT used: it false-positives on legit HTML
# placeholder="..." attributes and on AI self-explanation comments. Only
# "placeholder for" (comment stub: "Placeholder for unit selection logic")
# is a genuine stub signal.
PLACEHOLDER_PATTERNS = [
    r"\bnot implemented\b", r"placeholder\s+for\b",
    r"\bcoming soon\b", r"\blorem ipsum\b", r"\bunimplemented\b",
    r"throw new Error\(['\"]not", r"console\.log\(['\"]stub",
]

# Real critical security patterns that make a build genuinely unsafe to run.
# NOTE: bare `exec\s*\(` is NOT included — it false-positives on the safe,
# ubiquitous RegExp.prototype.exec() call (the VACA CodeScanner flags those as
# command injection, which sank every markdown-style build's scan).
CRITICAL_SEC_PATTERNS = [
    (r"\beval\s*\(", "eval() usage"),
    (r"new\s+Function\s*\(", "Function constructor (dynamic code)"),
    (r"child_process\s*\.", "child_process usage"),
    (r"(SELECT|INSERT|UPDATE|DELETE)\s+[^'\"]*\+\s*['\"]", "SQL string concatenation"),
]

# Advisory (non-fatal) security notes — documented, not a build failure.
ADVISORY_SEC_PATTERNS = [
    (r"\.innerHTML\s*=", ".innerHTML assignment (XSS advisory)"),
    (r"\.cookie\s*=", "document.cookie write (advisory)"),
]


class ScriptCounter(HTMLParser):
    """Count real <script> tags, ignoring literal '</script>' inside JS strings."""
    def __init__(self):
        super().__init__()
        self.open = 0
        self.close = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.open += 1

    def handle_endtag(self, tag):
        if tag == 'script':
            self.close += 1


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


# Locate the TypeScript compiler (used for the authoritative source-compile check).
TSC_BIN = None
for _cand in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "node_modules", "typescript", "bin", "tsc"),
    "/home/final-flash1/Desktop/visual-ai-architect/node_modules/typescript/bin/tsc",
]:
    _cand = os.path.normpath(_cand)
    if os.path.isfile(_cand):
        TSC_BIN = _cand
        break


def ts_compiles(out_dir):
    """Run `tsc --noEmit` on a project dir. Returns (ok, [errors]) or (None, reason)."""
    if not TSC_BIN:
        return None, "typescript compiler not available"
    tsconfig = os.path.join(out_dir, "tsconfig.json")
    if not os.path.isfile(tsconfig):
        return None, "no tsconfig.json in project"
    try:
        # --allowImportingTsExtensions: generated code imports sibling files with
        # explicit '.ts'/'.js' suffixes (e.g. `import { x } from './timer-input.ts'`)
        # and the generated tsconfig does not enable it. It is only legal with
        # --noEmit, which is exactly what we run here.
        r = subprocess.run(
            ["node", TSC_BIN, "--noEmit", "--allowImportingTsExtensions", "-p", out_dir],
            capture_output=True, text=True, timeout=180, cwd=out_dir,
        )
    except FileNotFoundError:
        return None, "node not available"
    except subprocess.TimeoutExpired:
        return False, ["tsc --noEmit timed out"]
    if r.returncode == 0:
        return True, []
    combined = (r.stderr or "") + (r.stdout or "")
    errs = [ln.strip() for ln in combined.splitlines() if "error TS" in ln]
    return False, (errs[:6] if errs else ["tsc --noEmit failed"])


def find_index_html(out_dir):
    """Locate the generated preview HTML. The per-file scaffolder writes it to
    src/app-preview-auto-generated/index.html (nested under the project name)."""
    if not out_dir or not os.path.isdir(out_dir):
        return None
    # Exact known location first (fast path)
    candidates = [
        os.path.join(out_dir, "index.html"),
        os.path.join(out_dir, "src", "app-preview-auto-generated", "index.html"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # Recursive fallback (any index.html one or two levels deep)
    for root, _dirs, files in os.walk(out_dir):
        if "index.html" in files and root != out_dir:
            return os.path.join(root, "index.html")
    return None


def scan_build(b):
    """Static-scan one build directory. Returns a result dict."""
    slug = b.get("slug")
    out_dir = b.get("outputDir", "")
    name = b.get("name", slug)
    checks = {}
    problems = []

    if b.get("status") != "built":
        checks["build_status"] = "fail"
        problems.append(f"build failed: {b.get('error','')[:200]}")
        return {"slug": slug, "name": name, "tier": b.get("tier"), "pass": False,
                "checks": checks, "problems": problems, "outputDir": out_dir}

    # 1. index.html present
    index_path = find_index_html(out_dir)
    if not index_path:
        checks["index_html"] = "fail"
        problems.append("index.html missing")
        index_html = ""
    else:
        index_html = open(index_path, encoding="utf-8", errors="replace").read()
        size = len(index_html)
        checks["index_html"] = "pass" if size > 500 else "fail"
        if size <= 500:
            problems.append(f"index.html too small ({size} bytes)")

    # 2. HTML structure
    if index_html:
        ok = ("<!doctype html" in index_html.lower() or "<html" in index_html.lower()) \
             and "<body" in index_html.lower()
        counter = ScriptCounter()
        counter.feed(index_html)
        ok = ok and counter.open == counter.close and counter.open >= 1
        checks["html_structure"] = "pass" if ok else "fail"
        if not ok:
            problems.append(f"html structure invalid (script tags open={counter.open} close={counter.close})")

    # 3. Source compiles: tsc --noEmit on the project (authoritative for TS).
    #    The preview HTML inlines raw TypeScript — node --check cannot parse it,
    #    so the compile signal comes from the project's own tsconfig instead.
    if out_dir and os.path.isdir(out_dir):
        ts_ok, ts_errs = ts_compiles(out_dir)
        if ts_ok is None:
            checks["ts_compiles"] = "skip"
        elif ts_ok:
            checks["ts_compiles"] = "pass"
        else:
            checks["ts_compiles"] = "fail"
            problems.append("tsc: " + "; ".join(ts_errs[:3]))

    # 4. Placeholder stubs (scan all source files)
    stub_hits = []
    if out_dir and os.path.isdir(out_dir):
        for root, _dirs, files in os.walk(out_dir):
            for fn in files:
                if not fn.endswith((".ts", ".js", ".html", ".css", ".py", ".go", ".sql", ".json")):
                    continue
                p = os.path.join(root, fn)
                try:
                    content = open(p, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                if not content.strip():
                    stub_hits.append(f"{fn}: empty")
                    continue
                for pat in PLACEHOLDER_PATTERNS:
                    if re.search(pat, content, re.I):
                        stub_hits.append(f"{fn}: matched '{pat}' pattern")
    checks["no_stubs"] = "pass" if not stub_hits else "fail"
    if stub_hits:
        problems.append("stubs: " + "; ".join(stub_hits[:5]))

    # 5. Security: scan source files for REAL critical patterns. Manifest counts
    #    are NOT trusted — VACA's own CodeScanner over-flags (RegExp.exec() →
    #    command injection, .innerHTML → XSS "high" on every build), which would
    #    fail all 50 builds and drown the real signal.
    critical_hits = []
    advisory_hits = []
    if out_dir and os.path.isdir(out_dir):
        for root, _dirs, files in os.walk(out_dir):
            for fn in files:
                if not fn.endswith((".ts", ".js", ".py", ".go", ".rs", ".html")):
                    continue
                p = os.path.join(root, fn)
                try:
                    content = open(p, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                for pat, label in CRITICAL_SEC_PATTERNS:
                    for m in re.finditer(pat, content, re.I):
                        ln = content.count("\n", 0, m.start()) + 1
                        critical_hits.append(f"{fn}:{ln} {label}")
                        break  # one hit per pattern per file
                for pat, label in ADVISORY_SEC_PATTERNS:
                    if re.search(pat, content, re.I):
                        advisory_hits.append(label)
                        break
    if critical_hits:
        checks["security"] = "fail"
        problems.append("security: " + "; ".join(critical_hits[:4]))
    else:
        checks["security"] = "pass"
        if advisory_hits:
            problems.append("advisory: " + ", ".join(dict.fromkeys(advisory_hits))[:160])

    # 6. Non-zero source file count
    if b.get("totalFiles", 0) > 0:
        checks["files_generated"] = "pass"
    else:
        checks["files_generated"] = "fail"
        problems.append("no files generated")

    # 'skip' (e.g. node unavailable) must NOT fail the build — only explicit fails do.
    passed = all(v != "fail" for v in checks.values())
    return {"slug": slug, "name": name, "tier": b.get("tier"), "pass": passed,
            "checks": checks, "problems": problems, "outputDir": out_dir,
            "totalFiles": b.get("totalFiles", 0), "totalChars": b.get("totalChars", 0)}


def write_wiki(result, build):
    """Write a wiki page for the build."""
    os.makedirs(WIKI_DIR, exist_ok=True)
    slug = result["slug"]
    name = result["name"]
    tier = result["tier"]
    path = os.path.join(WIKI_DIR, f"{slug}.md")
    date = datetime.utcnow().strftime("%Y-%m-%d")
    checks = result.get("checks", {})

    if result["pass"]:
        summary = "\n".join(f"- ✅ {k}: pass" for k, v in checks.items() if v == "pass")
        content = f"""# {name}

> **Build:** PASS · **Tier:** {tier} · **Date:** {date}
> **Output:** `{result.get('outputDir','')}`

## What it is

{name} — generated end-to-end by VACA through the per-file scaffold pipeline.

## Verification

{summary}

## Generated Architecture

- **Files:** {result.get('totalFiles', 0)} · **Code chars:** {result.get('totalChars', 0)}
- Full project in the output directory above (per-node source files + `index.html` preview).

---
*VACA 50-build campaign — verified {date}*
"""
    else:
        problems = "\n".join(f"- {p}" for p in result.get("problems", []))
        content = f"""# {name}

> **Build:** NEEDS REPAIR · **Tier:** {tier} · **Date:** {date}
> **Output:** `{result.get('outputDir','')}`

## What it is

{name} — generated by VACA through the per-file scaffold pipeline, but the static
scan flagged issues.

## Why it broke

{problems}

## Fix applied

*(to be filled by the repair pass — see `data/campaign50-repairs.md`)*

## Lesson for VACA

*(to be filled by the repair pass)*

---
*VACA 50-build campaign — flagged {date}*
"""
    with open(path, "w") as f:
        f.write(content)
    return path


def write_report(results, manifest):
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    tiers = Counter(r["tier"] for r in results)
    passed = [r for r in results if r["pass"]]
    failed = [r for r in results if not r["pass"]]
    date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    lines = [
        "# VACA 50-Build Campaign — Scan Report",
        "",
        f"- **Date:** {date}",
        f"- **Total builds:** {len(results)}",
        f"- **Passed:** {len(passed)}",
        f"- **Failed (need repair):** {len(failed)}",
        f"- **Tier breakdown:** {dict(tiers)}",
        "",
        "## Summary",
        "",
        f"Success rate: **{len(passed)/max(len(results),1)*100:.1f}%**",
        "",
        "## Failed builds (repair queue)",
        "",
    ]
    if failed:
        for r in failed:
            lines.append(f"- **{r['name']}** ({r['tier']}): {'; '.join(r['problems'][:3])}")
    else:
        lines.append("None — all builds passed the static scan. 🎉")
    lines += ["", "---", "*Generated by `scripts/scan-campaign-50.py`*", ""]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    return REPORT


def main(wiki_only=False):
    manifest = load_json(MANIFEST, {"builds": []})
    builds = manifest.get("builds", [])
    if not builds:
        print("No builds in manifest yet — run the campaign first.")
        sys.exit(1)

    if wiki_only:
        # Only write wikis from an existing scan file
        scan = load_json(SCAN_OUT, {"results": []})
        for r in scan.get("results", []):
            b = next((x for x in builds if x.get("slug") == r.get("slug")), {})
            write_wiki(r, b)
        print(f"✅ Wrote {len(scan.get('results',[]))} wiki pages (wiki-only mode)")
        return

    results = []
    for b in builds:
        r = scan_build(b)
        results.append(r)
        st = "✅" if r["pass"] else "❌"
        probs = f" — {'; '.join(r['problems'][:2])}" if not r["pass"] else ""
        print(f"  {st} {r['name']} [{r['tier']}]{probs}")

    # Persist scan + wikis
    os.makedirs(os.path.dirname(SCAN_OUT), exist_ok=True)
    with open(SCAN_OUT, "w") as f:
        json.dump({"scannedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                   "results": results}, f, indent=2)

    for r in results:
        b = next((x for x in builds if x.get("slug") == r.get("slug")), {})
        write_wiki(r, b)

    report = write_report(results, manifest)
    passed = sum(1 for r in results if r["pass"])
    print(f"\n=== Scan complete: {passed}/{len(results)} passed ===")
    print(f"    Scan data: {SCAN_OUT}")
    print(f"    Wiki dir:  {WIKI_DIR}")
    print(f"    Report:    {report}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki-only", action="store_true")
    args = ap.parse_args()
    main(wiki_only=args.wiki_only)
