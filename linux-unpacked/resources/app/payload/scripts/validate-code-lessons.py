#!/usr/bin/env python3
"""
Validate Code-Lessons Samples
==============================
Syntax-checks every concrete code sample in the generated code-lessons
training examples (training/dataset/code-lessons-examples.jsonl) so broken
ground truth never poisons the fine-tune:

  Python      → python3 -m py_compile
  Go          → gofmt -e            (parse-only — per-file samples intentionally
                                     omit imports, so a full `go build` would
                                     fail on missing deps, not syntax)
  TypeScript  → npx tsc --noEmit --strict --lib ES2020,DOM  (single-file check)
  SQL         → sqlite3 :memory:    (executes DDL — all SQL samples are CREATE
                                     TABLE/INDEX statements, safe to run)
  C#          → structural check    (balanced delimiters / unclosed strings;
                                     full compile needs a dotnet toolchain)

Prose rule-of-thumb examples (no language in their source tag) are skipped.

Usage:
  python3 scripts/validate-code-lessons.py [--jsonl PATH] [--quiet]
Exit code is non-zero if any sample fails its check, so CI / the generator can
block on broken lesson code.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_JSONL = ROOT / "training" / "dataset" / "code-lessons-examples.jsonl"

# Source-tag suffix → (language, checker name)
LANG_HINTS = [
    ("(Go)", "go"),
    ("(TypeScript)", "typescript"),
    ("(Python)", "python"),
    ("(SQL)", "sql"),
    ("C# idioms", "csharp"),
    ("(C#)", "csharp"),
]


def detect_language(source: str):
    for hint, lang in LANG_HINTS:
        if hint in source:
            return lang
    return None


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ─── Per-language checkers ───────────────────────────────────────────────────

def check_python(code: str):
    import py_compile
    # Compile inside a throwaway temp dir so the generated .pyc is cleaned up
    # with the directory (no __pycache__ litter in /tmp).
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "sample.py"
        src.write_text(code, encoding="utf-8")
        try:
            py_compile.compile(str(src), doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            return False, str(e)


def check_go(code: str):
    if not shutil.which("gofmt"):
        return None, "gofmt not available — skipped"
    with tempfile.NamedTemporaryFile("w", suffix=".go", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        # -e reports all parse errors; gofmt is parse-only so missing imports
        # (intentional in per-file samples) never fail this check.
        res = run(["gofmt", "-e", path])
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()
    finally:
        Path(path).unlink(missing_ok=True)


def check_typescript(code: str):
    if not shutil.which("npx"):
        return None, "npx not available — skipped"
    with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        res = run([
            "npx", "tsc", "--noEmit", "--strict", "--target", "ES2020",
            "--lib", "ES2020,DOM", "--module", "esnext", "--skipLibCheck", path,
        ], cwd=str(ROOT))
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()
    finally:
        Path(path).unlink(missing_ok=True)


def check_sql(code: str):
    """Execute the sample in a throwaway sqlite3 DB. NOTE: this validates the
    SQLite dialect — keep samples SQLite-compatible (avoid SERIAL, :: casts,
    and other PostgreSQL-only syntax) or this check will false-fail them."""
    if not shutil.which("sqlite3"):
        return None, "sqlite3 not available — skipped"
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        # :memory: executes the DDL in a throwaway DB — all samples are CREATE
        # TABLE/INDEX statements, so executing them is safe and validates syntax.
        res = run(["sqlite3", ":memory:", f".read {path}"])
        return res.returncode == 0, res.stderr.strip() or res.stdout.strip()
    finally:
        Path(path).unlink(missing_ok=True)


def check_csharp(code: str):
    """Structural check only (no dotnet toolchain): balanced delimiters and
    no unclosed string literals. Catches truncation/brace-loss defects.
    // comments and single-quoted char literals are stripped first so they
    can't cause false failures (e.g. a comment containing an unbalanced brace)."""
    errors = []
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    for ln_no, raw in enumerate(code.split("\n"), 1):
        line = raw.split("//", 1)[0]  # strip // comments
        i = 0
        in_string = False
        while i < len(line):
            ch = line[i]
            if ch == '"':
                in_string = not in_string  # plain double-quoted strings pair
            elif not in_string and ch == "'" and i + 2 < len(line) and line[i + 2] == "'":
                i += 2  # char literal like '{' — skip the whole literal
            elif not in_string and ch in "([{":
                stack.append(ch)
            elif not in_string and ch in ")]}":
                if not stack or stack[-1] != pairs[ch]:
                    errors.append(f"line {ln_no}: unmatched '{ch}'")
                    return False, "; ".join(errors)
                stack.pop()
            i += 1
        if in_string:
            errors.append(f"line {ln_no}: unclosed string literal")
    if stack:
        errors.append(f"unclosed delimiter(s): {''.join(stack)}")
    if errors:
        return False, "; ".join(errors)
    return True, "structural check passed (no dotnet toolchain available)"


CHECKERS = {
    "python": check_python,
    "go": check_go,
    "typescript": check_typescript,
    "sql": check_sql,
    "csharp": check_csharp,
}


def validate(jsonl: Path, quiet: bool = False) -> int:
    """Validate every code sample in the JSONL. Returns 0 (ok), 1 (failures),
    or 2 (missing file). Callable both from the CLI and from the generator."""
    if not jsonl.exists():
        print(f"FATAL: {jsonl} not found — run generate-code-lessons-examples.py first")
        return 2

    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    checked = skipped = 0
    failures = []

    for r in rows:
        lang = detect_language(r.get("source", ""))
        if lang is None:
            # A row that looks like code (multi-line, braces) but has no
            # language hint is probably a typo'd source tag — warn instead of
            # silently skipping it as prose.
            output = r.get("output", "")
            looks_like_code = "\n" in output and (
                "{" in output or "def " in output or "func " in output or "CREATE TABLE" in output
            )
            if looks_like_code:
                print(f"  ⚠  {r.get('source', '?')} — code-like output but no language tag "
                      f"matched; skipped unvalidated (fix the source tag or add a hint)")
            skipped += 1  # prose rule, not a code sample
            continue
        code = r.get("output", "")
        if not code.strip():
            failures.append((r.get("source", "?"), "empty output"))
            continue
        ok, detail = CHECKERS[lang](code)
        if ok is None:
            skipped += 1
            if not quiet:
                print(f"  ⏭  {r['source']} — {detail}")
            continue
        checked += 1
        status = "✅" if ok else "❌"
        print(f"  {status} [{lang:>10}] {r['source']}")
        if not ok:
            failures.append((r.get("source", "?"), detail))
            if not quiet:
                print(f"      {detail[:400]}")

    print(f"\nValidated {checked} code samples ({skipped} skipped: prose/skipped toolchain)")
    if failures:
        print(f"FAIL: {len(failures)} sample(s) failed validation:")
        for src, detail in failures:
            print(f"  - {src}: {detail[:200]}")
        return 1
    print("All samples valid ✓")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    quiet = "--quiet" in args
    jsonl = Path((args[args.index("--jsonl") + 1] if "--jsonl" in args else DEFAULT_JSONL))
    return validate(jsonl, quiet=quiet)


if __name__ == "__main__":
    sys.exit(main())
