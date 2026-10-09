#!/usr/bin/env python3
"""
Export corrected campaign-50 builds → training dataset (Track 4)
================================================================
Routes the POST-REPAIR campaign-50 builds (systematic errors eliminated:
index.ts entry points compile, cross-node TS2307 imports are fixed) into the
training dataset used to fine-tune the local model.

Why this matters:
  - The campaign scan proved the remaining failures are genuine AI output
    slips (TS1005 JSX-in-ts, TS1434/TS1435 prose, stubs), NOT pipeline bugs.
  - Those are exactly the habits a fine-tune should unlearn. The corrected
    per-node source files are the POSITIVE examples the model should mirror.

Quality filter per file (mirrors the campaign scan's failure signals):
  - Skip preview wrappers / README / config / non-source files
  - Skip stub code (not implemented, placeholder for, coming soon, lorem,
    unimplemented, throw new Error('not', TODO: Implement)
  - Skip JSX-in-.ts files (the TS1005 failure mode)
  - Skip files with markdown-prose lines (TS1434/TS1435 failure mode)

Output format matches training/dataset/train.jsonl:
  {"instruction": ..., "input": ..., "output": ...}

Writes training/dataset/campaign50-corrected.jsonl (separate file — never
clobbers the existing train.jsonl) and prints a summary.

Usage:
  python3 scripts/export-corrected-builds-to-training.py
"""

import json, os, re, sys, collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "data", "campaign50-manifest.json")
OUT = os.path.join(BASE, "training", "dataset", "campaign50-corrected.jsonl")

STUB_PATTERNS = [
    r"\bnot implemented\b", r"placeholder\s+for\b", r"\bcoming soon\b",
    r"\blorem ipsum\b", r"\bunimplemented\b",
    r"throw new Error\(['\"]not", r"TODO:\s*Implement",
]

# JSX-in-ts: only flag opening tags with attributes (<div className="x">) and
# closing tags (</div>) — NOT generics like Promise<Foo>/Map<string> (those
# have no whitespace after the tag name). The TS1005 failure mode is the model
# emitting real JSX elements into .ts files.
JSX_RE = re.compile(r"</?[a-z][a-z0-9]*\s[^>]*>|</[a-z][a-z0-9]*\s*>")

# Prose lines that break tsc (TS1434/TS1435) — markdown bullets, bold, notes
PROSE_RE = re.compile(r"^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|The .* (?:function|class|module))")

# Files we never want as training examples
SKIP_RE = re.compile(r"(app-preview-auto-generated|README|\.gitignore|package\.json|tsconfig|index\.html$|\.md$|__init__\.py$)")


def is_stub(code: str) -> bool:
    for pat in STUB_PATTERNS:
        if re.search(pat, code, re.I):
            return True
    return False


def has_jsx_in_ts(code: str) -> bool:
    # strip string literals then look for real JSX element tags (generics like
    # Promise<Foo> / Map<string> have no whitespace and are NOT flagged)
    stripped = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "", code)
    return bool(JSX_RE.search(stripped))


def has_prose(code: str) -> bool:
    for line in code.split("\n"):
        t = line.strip()
        if not t:
            continue
        # only flag lines that start a markdown/prose run and are NOT code
        if PROSE_RE.match(line) and not re.search(r"[;{}()=<>]", t):
            return True
    return False


def build_instruction(app_name: str, label: str, tier: str, lang: str) -> str:
    return (
        f"Generate the source file for the node '{label}' in the '{app_name}' "
        f"app ({tier} tier). Write complete, production-ready {lang} code that "
        f"exports named symbols only, includes NO import statements (the build "
        f"system adds them automatically), NO JSX (build the DOM with "
        f"document.createElement), and includes error handling and edge cases. "
        f"Return only the code — no markdown, no explanations."
    )


def main():
    if not os.path.isfile(MANIFEST):
        print("No manifest found — run the campaign first.")
        sys.exit(1)

    with open(MANIFEST) as f:
        manifest = json.load(f)

    entries = []
    skipped = collections.Counter()
    per_build = collections.Counter()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    for b in manifest.get("builds", []):
        if b.get("status") != "built":
            skipped["not-built"] += 1
            continue
        out_dir = b.get("outputDir", "")
        name = b.get("name", b.get("slug", "?"))
        tier = b.get("tier", "simple")
        if not out_dir or not os.path.isdir(out_dir):
            skipped["no-output"] += 1
            continue

        build_count = 0
        for root, _dirs, files in os.walk(out_dir):
            for fn in files:
                if not fn.endswith(".ts"):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), out_dir).replace("\\", "/")
                if SKIP_RE.search(rel):
                    continue
                try:
                    with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as fh:
                        code = fh.read()
                except Exception:
                    continue
                if len(code.strip()) < 80:
                    skipped["tiny"] += 1
                    continue
                if is_stub(code):
                    skipped["stub"] += 1
                    continue
                if has_jsx_in_ts(code):
                    skipped["jsx-in-ts"] += 1
                    continue
                if has_prose(code):
                    skipped["prose"] += 1
                    continue

                # node label ≈ directory name (src/<node>/<file>.ts)
                parts = rel.split("/")
                label = parts[1] if len(parts) >= 3 else fn.replace(".ts", "")
                lang = "TypeScript"
                entries.append({
                    "instruction": build_instruction(name, label, tier, lang),
                    "input": "",
                    "output": code,
                })
                build_count += 1
        per_build[name] = build_count

    with open(OUT, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"✅ Wrote {len(entries)} examples → {OUT}")
    print(f"   Skipped: {dict(skipped)}")
    print(f"   Builds contributing: {sum(1 for v in per_build.values() if v > 0)}/{len(manifest.get('builds', []))}")
    print("   Top contributing builds:")
    for name, cnt in sorted(per_build.items(), key=lambda kv: -kv[1])[:8]:
        print(f"     - {name}: {cnt} file(s)")


if __name__ == "__main__":
    main()
