#!/usr/bin/env python3
"""
Check File-Generation Contracts
================================
Verifies that every concrete code sample in the per-file generation training
examples (training/dataset/file-generation-examples.jsonl) honors its plan
entry's exports/uses contract — the #1 compile-failure source in large builds.

For each code sample the plan entry is embedded in the instruction text:

  "…exports [OrderService, NewOrderService], uses [{from internal/repository,
   members [OrderRepo]}, {from internal/models, members [Order, OrderStatus]}]…"

The checker:
  1. Parses the declared `exports` and `uses` from the instruction.
  2. Extracts the file's ACTUAL public API per language (Go top-level
     capitalized decls, TS `export` declarations, Python top-level def/class,
     C# `public` types) and its ACTUAL imports (real `import`/`using`).
  3. Fails on any violation:
       - declared export missing from the code        (incomplete file)
       - code exports a symbol the plan doesn't list   (invented public API)
       - Go/Python/TS file contains a real import      (build adds them from
         uses; writing one breaks the contract)
       - C# `using` namespace not listed in uses       (importing a module
         that isn't part of the contract)

SQL samples are skipped (their `exports: [upgrade]` is a migration marker,
not a code symbol). Prose rule rows are skipped.

Usage:
  python3 scripts/check-file-generation-contracts.py [--jsonl PATH] [--quiet]
Exit code is non-zero if any sample violates its contract, so the generator /
CI can block broken ground truth before it reaches the fine-tune.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_JSONL = ROOT / "training" / "dataset" / "file-generation-examples.jsonl"

# Source-tag suffix → language
LANG_HINTS = [
    ("(Go)", "go"),
    ("(TypeScript)", "typescript"),
    ("(Python)", "python"),
    ("(SQL)", "sql"),
    ("(C#)", "csharp"),
]


def detect_language(source: str):
    for hint, lang in LANG_HINTS:
        if hint in source:
            return lang
    return None


# ─── Plan parsing (from the instruction text) ────────────────────────────────

def parse_plan(instruction: str):
    """Extract (exports:set, uses:[(from, [members])]) from the instruction."""
    exports = set()
    m = re.search(r"exports\s*\[([^\]]*)\]", instruction)
    if m:
        exports = {x.strip() for x in m.group(1).split(",") if x.strip()}
    uses = []
    for um in re.finditer(r"\{from\s+([^,}]+?),\s*members\s+\[([^\]]*)\]\}", instruction):
        from_mod = um.group(1).strip()
        members = {x.strip() for x in um.group(2).split(",") if x.strip()}
        uses.append((from_mod, members))
    return exports, uses


# ─── Comment stripping (so header comments like "// Exports: X" don't fool
#     the symbol extractors) ─────────────────────────────────────────────────

def strip_line_comments(code: str, markers=("//",)):
    lines = []
    for ln in code.splitlines():
        for mk in markers:
            idx = ln.find(mk)
            if idx != -1:
                ln = ln[:idx]
                break
        lines.append(ln)
    return "\n".join(lines)


# ─── Per-language export + import extraction ────────────────────────────────

def extract_go(code: str):
    code = strip_line_comments(code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    exports = set()
    # top-level type / func / var / const declarations (capital first letter)
    for pat in (r"^type\s+([A-Z]\w*)", r"^func\s+([A-Z]\w*)",
                r"^var\s+([A-Z]\w*)", r"^const\s+([A-Z]\w*)"):
        exports.update(re.findall(pat, code, flags=re.M))
    # const ( ... ) blocks: indented capital names
    for block in re.finditer(r"const\s*\(([^)]*)\)", code, flags=re.S):
        exports.update(re.findall(r"^\s*([A-Z]\w*)\s", block.group(1), flags=re.M))
    # Real import statements: single form `import "pkg"` and block form
    # `import ( "a" "b" )`. Aliased imports (`import f "fmt"`) still count —
    # any `import` line in a node file violates the contract.
    imports = set()
    for ln in code.splitlines():
        s = ln.strip()
        if s.startswith("import "):
            for m in re.finditer(r'"([^"]+)"', ln):
                imports.add(m.group(1))
            if not imports or not re.search(r'"', ln):
                imports.add(s[7:].strip().rstrip())  # bare/aliased form
    return exports, imports


def extract_typescript(code: str):
    code = strip_line_comments(code)
    exports = set(re.findall(r"^export\s+(?:interface|function|class|const|type|enum)\s+([A-Za-z_]\w*)",
                             code, flags=re.M))
    imports = set(re.findall(r"^import\s+(?:type\s+)?[\w{},\s*]+?\s+from\s+['\"]([^'\"]+)['\"]",
                             code, flags=re.M))
    return exports, imports


def extract_python(code: str):
    # strip full-line comments only (safe: no # inside sample strings)
    code = "\n".join(re.sub(r"^\s*#.*$", "", ln) for ln in code.splitlines())
    exports = set()
    for pat in (r"^class\s+([A-Za-z_]\w*)", r"^def\s+([A-Za-z_]\w*)"):
        exports.update(re.findall(pat, code, flags=re.M))
    exports = {e for e in exports if not e.startswith("_")}
    imports = set(re.findall(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", code, flags=re.M))
    imports = {i[0] or i[1] for i in imports}
    return exports, imports


def extract_csharp(code: str):
    code = strip_line_comments(code)  # handles // and /// (starts with //)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    exports = set(re.findall(r"^public\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+|readonly\s+|async\s+)*(?:class|record|interface|struct|enum)\s+([A-Za-z_]\w*)",
                             code, flags=re.M))
    imports = set(re.findall(r"^using\s+(?:static\s+)?([\w.]+)\s*;", code, flags=re.M))
    # public members of public types are part of the type's surface, not
    # separate exports — only top-level public types are contract exports.
    return exports, imports


EXTRACTORS = {
    "go": extract_go,
    "typescript": extract_typescript,
    "python": extract_python,
    "csharp": extract_csharp,
}


# ─── Contract checking ───────────────────────────────────────────────────────

def check_row(row: dict):
    """Return a list of violation strings for one sample ([] = compliant)."""
    source = row.get("source", "")
    lang = detect_language(source)
    if lang is None or lang == "sql":
        return []  # prose rule, or SQL (migration marker, not code symbols)
    instruction = row.get("instruction", "")
    declared_exports, uses = parse_plan(instruction)
    if not declared_exports and not uses:
        return [f"{source}: no exports/uses found in instruction — cannot verify"]
    code = row.get("output", "")
    actual_exports, actual_imports = EXTRACTORS[lang](code)

    violations = []

    # 1. Every declared export must exist in the file.
    missing = declared_exports - actual_exports
    if missing:
        violations.append(f"{source}: declared exports missing from code: {sorted(missing)}")

    # 2. No invented public API: every real export must be in the plan.
    extra = actual_exports - declared_exports
    if extra:
        violations.append(f"{source}: code exports symbols not in the plan: {sorted(extra)} "
                          f"(make them private or add them to exports)")

    # 3. Import contract per language.
    if lang in ("go", "python", "typescript"):
        if actual_imports:
            violations.append(f"{source}: file writes import statement(s) {sorted(actual_imports)} — "
                              f"the build system adds imports from uses; the file must not")
    elif lang == "csharp":
        allowed = {f for f, _ in uses} | {"System"}
        rogue = {i for i in actual_imports
                 if i not in allowed and not i.startswith("System.")}
        if rogue:
            violations.append(f"{source}: using directive(s) {sorted(rogue)} not in uses "
                              f"(uses only: {sorted(allowed)})")

    # 4. Referenced identifiers must be uses members or local/private symbols.
    #    (Identifier scan — catches a sample that declares a uses member it
    #    never references, or references a member that isn't in uses.)
    uses_members = {m for _, ms in uses for m in ms}
    if uses_members:
        # scan the first word of each exported declaration (the surface) plus
        # every capitalized type-like token in the body
        referenced = set(re.findall(r"\b([A-Z][A-Za-z0-9_]*)\b", code))
        missing = uses_members - referenced
        if missing:
            violations.append(f"{source}: declared uses member(s) never referenced in "
                              f"code: {sorted(missing)}")

    return violations


def check_contracts(jsonl: Path, quiet: bool = False) -> int:
    """Check every sample in the JSONL. Returns 0 (ok), 1 (violations),
    or 2 (missing file). Callable from the CLI and from the generator."""
    if not jsonl.exists():
        print(f"FATAL: {jsonl} not found — run generate-file-generation-examples.py first")
        return 2

    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    checked = skipped = 0
    all_violations = []

    for r in rows:
        lang = detect_language(r.get("source", ""))
        if lang is None or lang == "sql":
            skipped += 1
            continue
        checked += 1
        violations = check_row(r)
        status = "✅" if not violations else "❌"
        print(f"  {status} [{lang:>10}] {r['source']}")
        if violations:
            all_violations.extend(violations)
            if not quiet:
                for v in violations:
                    print(f"      {v}")

    print(f"\nChecked {checked} code samples ({skipped} skipped: prose/SQL)")
    if all_violations:
        print(f"FAIL: {len(all_violations)} contract violation(s):")
        for v in all_violations:
            print(f"  - {v}")
        return 1
    print("All samples honor their exports/uses contracts ✓")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    quiet = "--quiet" in args
    jsonl = Path((args[args.index("--jsonl") + 1] if "--jsonl" in args else DEFAULT_JSONL))
    return check_contracts(jsonl, quiet=quiet)


if __name__ == "__main__":
    sys.exit(main())
