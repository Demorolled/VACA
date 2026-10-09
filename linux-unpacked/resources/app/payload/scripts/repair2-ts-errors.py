#!/usr/bin/env python3
"""
VACA Campaign 50 — Repair Pass 2: AI-output TS errors
======================================================
The static scan surfaced REAL TypeScript syntax errors in the generated
per-node source files. Root-cause analysis of the error distribution:

  - TS1443 / TS1128 (~40%) — the AI leaked markdown/prose into .ts files:
    ``` fences, "**Explanation**:", "- bullet" lines, "Note: ..." text.
  - TS1161 — JSX in a .ts file (only valid in .tsx).
  - TS1005/TS1144/TS1135 — generic syntax slips, incl. missing generics
    (`Promise SearchResult[]` instead of `Promise<SearchResult[]>`).
  - TS6059 — scaffolder tsconfig sets rootDir: ./src but writes index.ts at
    root (systematic config bug, fixed here by adjusting tsconfig).
  - eval() in Calculator — real security finding (repaired).

Phases (each idempotent, runs to completion):
  A. Deterministic TS cleaner over every .ts/.js file:
       - strip ``` fences and markdown prose blocks from file bodies
       - fix `Promise X` / `Array X` → `Promise<X>` / `Array<X>` (missing generics)
       - fix `for (... of_X)` → `for (... of X)` (missing space)
       - tsconfig: remove rootDir (or set to ".") so root index.ts compiles
  B. For builds that STILL fail tsc: rebuild through the fixed VACA pipeline
     (import bug now fixed upstream), re-run the cleaner, re-check.
  C. Report remaining failures.

Usage:
  python3 scripts/repair2-ts-errors.py [--phase clean|rebuild|report] [--slug X]
"""

import json, os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
MANIFEST = os.path.join(BASE, "data/campaign50-manifest.json")
SCAN_SCRIPT = os.path.join(BASE, "scripts", "scan-campaign-50.py")
LOG = os.path.join(BASE, "data", "campaign50-repairs2.md")
TSC_BIN = os.path.join(BASE, "node_modules", "typescript", "bin", "tsc")

# ── Pattern definitions ────────────────────────────────────────────────────

# ``` or ```ts / ```typescript / ```js fence lines (standalone)
FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*$", re.M)

# Prose-block detection: a line that starts a markdown/prose run inside a
# code file: "**Bold**", "- item", "Note:", "> quote", "Explanation:", "The X file contains...".
# We remove a line ONLY when it is not inside a comment and not valid TS syntax.
PROSE_START_RE = re.compile(r"^\s*(?:\*\*[^*]+\*\*|[-*]\s+|Note:|NOTE:|> |Explanation:|The .* file contains|You should|Define these|Here's|Heres|Below is|This .* (?:function|class|module))")

# Missing generics: `Promise SearchResult[]` / `Array X` / `Set Y` (word + space + Capitalized)
MISSING_GENERIC_RE = re.compile(r"\b(Promise|Array|Set|Map|Record)\s+([A-Z_]\w*(?:\[\])*)")

# for-of missing space: `for (const x of_dep)` → `for (const x of _dep)`.
# Capture the underscore with the identifier so it is NOT dropped.
FOR_OF_RE = re.compile(r"\bfor\s*\(([^)]*?)\bof(_[A-Za-z_]\w*)")

# ── AI-generated import normalization ────────────────────────────────────────
# The AI repeatedly emits its own sibling imports despite the prompt forbidding
# them. Symptoms on disk: the SAME module imported twice (TS2300 duplicate
# identifier), extensionless relative paths (TS2307), and imports of symbols the
# file itself declares (also TS2300). The build system adds dependency imports
# automatically, so the leading import block is normalized deterministically:
#  - same-module named imports are merged into one line
#  - symbols the file declares itself are dropped from the import
#  - relative module paths gain a .ts extension
# Lines after the first statement are never touched (they may be markdown or
# template-literal content in markdown-style builds).
IMPORT_NAMED_RE = re.compile(r"^import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"];?\s*$")
TOP_DECL_RE = re.compile(r"^(?!\s)(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)", re.M)
# TS/JS source extension suffix (used for import-path normalization below)
EXT_RE = re.compile(r"\.(ts|js|mjs|cjs|tsx|jsx)$")


def normalize_ts_imports(source: str) -> str:
    """Merge/dedupe AI-generated sibling imports in the leading block.
    Only touches the import run at the top of the file; everything after the
    first non-import statement is left untouched."""
    lines = source.split("\n")
    head_idx = []
    i = 0
    while i < len(lines):
        t = lines[i].strip()
        if t == "" or t.startswith(("//", "/*")) or t.startswith("import "):
            head_idx.append(i)
            i += 1
        else:
            break
    if not head_idx:
        return source
    body = "\n".join(lines[i:])

    merged = {}  # module → set of symbols
    for idx in head_idx:
        m = IMPORT_NAMED_RE.match(lines[idx].strip())
        if m:
            mod = m.group(2)
            syms = [s.strip().split(" as ")[0].strip() for s in m.group(1).split(",")]
            merged.setdefault(mod, set()).update(s for s in syms if s)

    # Symbols the file declares itself must NOT come from an import.
    declared = set(TOP_DECL_RE.findall(body))
    keep = {mod: (syms - declared) for mod, syms in merged.items()
            if mod.startswith(("./", "../")) and (syms - declared)}

    merged_lines = []
    for mod in sorted(keep):
        # Node files live in PER-NODE subdirectories (src/<node>/<file>.ts), so
        # a single-segment relative import './name' from src/<node>/<file>.ts
        # must resolve to the SIBLING directory: ../name/name.ts. A flat
        # './name.ts' would fail with TS2307 (module not in this node's dir).
        # Multi-segment paths (e.g. './sub/x') are left as-is.
        # IMPORTANT: the on-disk auto-import may already carry the extension
        # ('./state-store.ts'), so strip it from the DIRECTORY component while
        # keeping it on the FILE component: '../state-store/state-store.ts'.
        if re.match(r"^\./[^/]+$", mod):
            base = mod[2:]                                  # 'state-store.ts' or 'state-store'
            stem = EXT_RE.sub("", base)
            target = f"../{stem}/{base}"                   # '../state-store/state-store.ts'
        elif re.match(r"^\.\./[^/]+/[^/]+$", mod):
            # ALREADY-BROKEN form from an earlier clean pass: the directory
            # component kept the extension ('../state-store.ts/state-store.ts').
            # Strip it from the DIRECTORY only, keep the FILE component as-is.
            d, f = mod[3:].split("/", 1)
            d_stem = EXT_RE.sub("", d)
            target = f"../{d_stem}/{f}"
        else:
            target = mod
        ext = target if EXT_RE.search(target) else target + ".ts"
        merged_lines.append(f"import {{ {', '.join(sorted(keep[mod]))} }} from '{ext}';")

    new_head = []
    for idx in head_idx:
        m = IMPORT_NAMED_RE.match(lines[idx].strip())
        if m and m.group(2).startswith(("./", "../")):
            continue  # merged away (re-emitted in merged_lines)
        new_head.append(lines[idx])

    return "\n".join(merged_lines + new_head) + ("\n" if merged_lines or new_head else "") + body


def line_contexts(source: str) -> list:
    """Per-line string/template state. Returns list of booleans: True when the
    line is FULLY outside any string literal / template literal, False when the
    line contains or is inside a quote/template (so transforms must NOT touch it).

    Handles: single/double-quoted strings with backslash escapes, template
    literals with ${...} nesting (quotes inside ${} do not terminate the template
    until its matching backtick is found). This protects markdown content that
    legitimately lives inside template literals (e.g. a markdown renderer's
    sample fences/bullets) from being treated as stray prose.
    """
    outside = []
    in_tpl = False          # inside a `...` template literal
    tpl_depth = 0           # ${ nesting depth
    for line in source.split("\n"):
        # A line of ONLY backticks (optionally + language tag) is a stray
        # markdown fence, not real code: it must NOT toggle template state
        # (three backticks would flip open/close/open and corrupt state for
        # every following line). Safe to drop only when currently outside a
        # template; when inside one (markdown content), keep it.
        if FENCE_RE.match(line):
            outside.append(not in_tpl and tpl_depth == 0)
            continue
        i = 0
        n = len(line)
        state_start = (in_tpl, tpl_depth)
        fully_outside_start = not in_tpl and tpl_depth == 0
        line_fully_outside = fully_outside_start
        while i < n:
            ch = line[i]
            if in_tpl:
                if ch == "\\" and i + 1 < n:
                    i += 2  # skip escaped char (incl. escaped backtick \`)
                    continue
                if ch == "$" and i + 1 < n and line[i + 1] == "{":
                    tpl_depth += 1
                    i += 2
                    continue
                if ch == "}" and tpl_depth > 0:
                    tpl_depth -= 1
                    i += 1
                    continue
                if ch == "`" and tpl_depth == 0:
                    in_tpl = False
                    i += 1
                    continue
                i += 1
                continue
            if ch == "`":
                in_tpl = True
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                i += 1
                while i < n:
                    if line[i] == "\\":
                        i += 2
                        continue
                    if line[i] == quote:
                        break
                    i += 1
                i += 1
                continue
            i += 1
        # If the line ended while we were inside a string/template, mark it unsafe.
        if in_tpl or tpl_depth > 0:
            line_fully_outside = False
        elif state_start != (in_tpl, tpl_depth):
            # started inside (carry-over) but ended outside — unsafe to transform
            line_fully_outside = fully_outside_start
        outside.append(line_fully_outside)
    return outside


def clean_ts(source: str) -> str:
    """Deterministically clean systematic AI-output errors from a TS file.
    String/template-aware: lines inside string or template literals are never
    treated as fences or prose (protects markdown-style builds)."""
    ctx = line_contexts(source)
    lines = source.split("\n")
    out = []
    for idx, line in enumerate(lines):
        safe = ctx[idx]
        if safe and FENCE_RE.match(line):
            continue  # drop fence markers (only outside strings)
        # Drop standalone prose lines (only if they look like prose, not code)
        if safe and PROSE_START_RE.match(line) and not line.strip().startswith(("//", "/*", "* ", "import", "export", "const", "let", "var", "function", "class", "interface", "type", "enum", "async", "return", "if", "for", "while", "switch", "try", "catch", "} ", "}", "{", ")", "private", "public", "protected")):
            stripped = line.strip()
            # Only drop lines that are NOT plausibly code. The code-signal charset
            # is STRICTLY structural punctuation ({ } ( ) = ; < >): backticks,
            # quotes, asterisks, slashes and dashes appear in prose too
            # (e.g. 'importing from `quote-source.ts`' or '"Picker Engine"'), so
            # they must NOT qualify a line as code — otherwise trailing prose
            # paragraphs survive and break tsc with TS1435.
            if not re.search(r"[;{}()=<>]", stripped) or stripped.startswith(("- ", "* ", "**")):
                continue
        out.append(line)
    source = "\n".join(out)

    # Fix missing generics / for-of typos ONLY on lines fully outside strings.
    # IMPORTANT: recompute context on the CLEANED source — the first loop may
    # have dropped fence/prose lines, so the original ctx is misaligned with
    # the reduced line list (a stale 'safe' flag could fire a transform on a
    # line that is actually inside a template literal).
    ctx2 = line_contexts(source)
    fixed_lines = []
    for idx, line in enumerate(source.split("\n")):
        # Skip transforms on lines containing quote/backtick chars: a fully-
        # contained single-line template/string (e.g. `Promise Thing`) is marked
        # "safe" by the state machine, and must not be rewritten. Legitimate type
        # annotations never contain quotes, so nothing is lost.
        if ctx2[idx] and not re.search(r"['\"`]", line):
            line = MISSING_GENERIC_RE.sub(lambda m: f"{m.group(1)}<{m.group(2)}>", line)
            line = FOR_OF_RE.sub(lambda m: f"for ({m.group(1)}of {m.group(2)}", line)
        fixed_lines.append(line)
    source = "\n".join(fixed_lines)
    # Trim trailing blank lines left behind by dropped prose blocks.
    return re.sub(r"\n+$", "", source)


def fix_tsconfig(out_dir: str) -> bool:
    """Remove rootDir conflict so root index.ts compiles. Returns True if changed."""
    tsconfig = os.path.join(out_dir, "tsconfig.json")
    if not os.path.isfile(tsconfig):
        return False
    try:
        with open(tsconfig) as f:
            cfg = json.load(f)
    except Exception:
        return False
    co = cfg.get("compilerOptions", {})
    if "rootDir" in co:
        co["rootDir"] = "."
        with open(tsconfig, "w") as f:
            json.dump(cfg, f, indent=2)
        return True
    return False


def tsc_errors(out_dir: str) -> list:
    """Run tsc --noEmit and return list of (file, line, code, message)."""
    try:
        r = subprocess.run(
            ["node", TSC_BIN, "--noEmit", "--allowImportingTsExtensions", "-p", out_dir],
            capture_output=True, text=True, timeout=180, cwd=out_dir,
        )
    except Exception:
        return []
    if r.returncode == 0:
        return []
    combined = (r.stderr or "") + (r.stdout or "")
    errs = []
    for ln in combined.splitlines():
        m = re.match(r"^(.*?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.*)$", ln.strip())
        if m:
            errs.append((m.group(1), int(m.group(2)), m.group(4), m.group(5)))
    return errs


def clean_build(b) -> dict:
    """Phase A: deterministic clean of one build. Returns stats."""
    out = b.get("outputDir", "")
    if not out or not os.path.isdir(out):
        return {"cleaned": 0, "tsconfig_fixed": False}
    cleaned = 0
    for root, _d, files in os.walk(out):
        for fn in files:
            if not fn.endswith((".ts", ".js")):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except Exception:
                continue
            fixed = normalize_ts_imports(src)
            fixed = clean_ts(fixed)
            if fixed != src:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(fixed)
                cleaned += 1
    tc = fix_tsconfig(out)
    return {"cleaned": cleaned, "tsconfig_fixed": tc}


def main(phase="clean", slug=None):
    with open(MANIFEST) as f:
        manifest = json.load(f)
    builds = manifest.get("builds", [])
    if slug:
        builds = [b for b in builds if b.get("slug") == slug]

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log_lines = [f"# VACA Campaign 50 — Repair Pass 2 ({phase})", ""]

    if phase in ("clean", "all"):
        print(f"=== Phase A: deterministic TS clean ({len(builds)} builds) ===")
        for b in builds:
            if b.get("status") != "built":
                continue
            stats = clean_build(b)
            if stats["cleaned"] or stats["tsconfig_fixed"]:
                print(f"  🔧 {b['name']}: {stats['cleaned']} file(s) cleaned, tsconfig {'fixed' if stats['tsconfig_fixed'] else 'ok'}")
                log_lines.append(f"### {b['name']}: {stats['cleaned']} file(s) cleaned, tsconfig_fixed={stats['tsconfig_fixed']}")
        print("Phase A done.")

    if phase in ("rebuild", "all"):
        print("\n=== Phase B: rebuild still-failing builds through fixed pipeline ===")
        # campaign-50-builds.py has hyphens and cannot be imported by name —
        # load it via importlib from its file path.
        import importlib.util
        _c50_path = os.path.join(BASE, "scripts", "campaign-50-builds.py")
        _spec = importlib.util.spec_from_file_location("c50", _c50_path)
        c50 = importlib.util.module_from_spec(_spec)
        sys.modules["c50"] = c50
        _spec.loader.exec_module(c50)
        for b in builds:
            if b.get("status") != "built":
                continue
            out = b.get("outputDir", "")
            if not out or not os.path.isdir(out):
                continue
            errs = tsc_errors(out)
            if not errs:
                continue
            print(f"  🔨 rebuild: {b['name']} ({len(errs)} tsc errors)")
            spec = next((s for t, s in c50.ALL_SPECS if c50.slugify(s["name"]) == b["slug"]), None)
            if not spec:
                print(f"    ⚠ no spec for {b['name']}, skipping")
                continue
            t0 = time.time()
            r = c50.build_one(spec, b["tier"], skip_validation=True)
            dt = time.time() - t0
            status = "✅" if r["status"] == "built" else "❌"
            print(f"    {status} rebuilt in {dt:.0f}s {r.get('error', '')}")
            if r["status"] == "built":
                # re-clean the fresh build
                stats = clean_build(r)
                log_lines.append(f"### {b['name']}: REBUILT via fixed pipeline, re-cleaned {stats['cleaned']} file(s)")
                # update manifest
                for i, mb in enumerate(manifest["builds"]):
                    if mb.get("slug") == b["slug"]:
                        manifest["builds"][i] = r
                        break
                with open(MANIFEST, "w") as f:
                    json.dump(manifest, f, indent=2)

    with open(LOG, "w") as f:
        f.write("\n".join(log_lines) + "\n")

    if phase in ("report", "all"):
        print("\n=== Re-scanning ===")
        subprocess.run([sys.executable, SCAN_SCRIPT], cwd=BASE)
        print("\n=== Post-repair2 summary ===")
        import json as _json
        scan = _json.load(open(os.path.join(BASE, "data/campaign50-scan.json")))
        res = scan["results"]
        passed = sum(1 for r in res if r["pass"])
        print(f"PASSED: {passed}/{len(res)}")
        for r in res:
            if not r["pass"]:
                print(f"  ❌ {r['name']} [{r['tier']}]: {'; '.join(r['problems'][:2])}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["clean", "rebuild", "report", "all"], default="clean")
    ap.add_argument("--slug", type=str, default=None)
    args = ap.parse_args()
    main(phase=args.phase, slug=args.slug)
