#!/usr/bin/env python3
"""smoke-test-cli.py — behavioral gate for generated CLI apps (non-HTML entries).

tsc cannot see whether a generated CLI app actually RUNS: a program that
imports a type-only member as a value (erased at runtime), references an
undefined symbol at module scope, or is a stub body (loadHabits = () => [],
saveHabits = () => {}) passes the type gate but crashes or does nothing when
executed. This probe executes the entry a few generic invocations under tsx
and reports a verdict + captured errors, mirroring smoke-test-html.py.

Usage:
    python3 scripts/smoke-test-cli.py <exportDir> [--entry src/main.ts] [--timeout 20]

Emits a single JSON object on stdout:
    {"status": "passed"|"failed"|"skipped"|"unavailable",
     "errors": [...], "detail": str, "runs": [{args, exit, timedOut, out}]}

Verdict rules (lenient on purpose — never blame the model for infra):
  * no runnable entry          -> skipped
  * tsx binary missing         -> unavailable (error key)
  * any invocation exits 0 with non-empty stdout -> passed
  * every invocation crashes / prints nothing / times out -> failed
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSX = ROOT / "node_modules" / ".bin" / "tsx"

# Entry discovery priority — the file the app is meant to be launched from.
ENTRY_NAMES = ("main", "index", "cli", "app", "server", "start")
ENTRY_RE = r"(^|/|\.)(?:%s)\.(?:ts|tsx|js|mjs|cjs)$"


def pick_entry(export_dir: Path, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    files = sorted(
        f for f in export_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in (".ts", ".tsx", ".js", ".mjs", ".cjs")
    )
    if not files:
        return None
    for name in ENTRY_NAMES:
        rx = re.compile(ENTRY_RE % re.escape(name), re.I)
        for f in files:
            if rx.search(str(f)):
                return str(f.relative_to(export_dir))
    return str(files[0].relative_to(export_dir))


def run_probe(entry_abs: Path, args: list[str], timeout: int) -> dict:
    """Execute the entry under tsx. stdin is closed so interactive prompts EOF
    immediately instead of hanging the probe."""
    try:
        p = subprocess.run(
            [str(TSX), str(entry_abs), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "args": args,
            "exit": p.returncode,
            "timedOut": False,
            "out": (p.stdout or "")[-2000:],
            "err": (p.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"args": args, "exit": None, "timedOut": True, "out": "", "err": f"timed out after {timeout}s"}


def looks_crashed(run: dict) -> bool:
    """A real crash, not a user-facing message. Uncaught JS errors print a stack
    (lines starting with whitespace then 'at ...'); a well-behaved CLI may print
    'Error: file not found' to stderr while running fine — that is NOT a crash."""
    blob = run["out"] + "\n" + run["err"]
    if "SyntaxError" in blob or "ReferenceError" in blob or "TypeError" in blob:
        return True
    # Node stack frames: "    at ModuleJob.run (node:internal/...)"
    if re.search(r"\n\s+at ", run["err"] or ""):
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("--entry", default=None)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    export_dir = Path(args.export_dir)
    entry_rel = pick_entry(export_dir, args.entry)
    if entry_rel is None:
        print(json.dumps({"status": "skipped", "errors": [], "detail": "no runnable entry file"}))
        return
    entry_abs = export_dir / entry_rel
    if not entry_abs.is_file():
        print(json.dumps({"status": "skipped", "errors": [], "detail": f"entry not on disk: {entry_rel}"}))
        return
    if not TSX.exists():
        print(json.dumps({"error": f"tsx binary not found at {TSX}"}))
        return

    # Probe generic invocations: most CLIs answer --help/-h; the bare run
    # catches hand-rolled arg parsers that print a menu/usage when invoked with
    # no flags (and would exit non-zero on an unimplemented --help).
    probes: list[list[str]] = [["--help"], ["-h"], []]
    runs = []
    for probe in probes:
        runs.append(run_probe(entry_abs, probe, args.timeout))

    passed = [r for r in runs if r["exit"] == 0 and r["out"].strip() and not looks_crashed(r)]
    if passed:
        first = passed[0]
        out_lines = [l.strip() for l in first["out"].splitlines() if l.strip()]
        detail = f"{entry_rel}: exit 0, {len(out_lines)} output line(s) [{probes[runs.index(first)][0]}]"
        print(json.dumps({"status": "passed", "errors": [], "detail": detail, "runs": runs}))
        return

    timed_out = all(r["timedOut"] for r in runs)
    errors: list[str] = []
    for r in runs:
        if r["timedOut"]:
            errors.append(f"invocation {r['args']} timed out")
        elif r["exit"] != 0:
            crash = next((l.strip() for l in r["err"].splitlines() if l.strip() and ("Error" in l or "error" in l or "at " in l)), None)
            errors.append(f"invocation {r['args']} exited {r['exit']}" + (f": {crash[:160]}" if crash else " with no output"))
        elif not r["out"].strip():
            errors.append(f"invocation {r['args']} exited 0 but printed NOTHING (blank/stub CLI)")

    if not errors:
        errors.append("all invocations exited 0 with empty output — app appears to be a stub")
    detail = (f"all invocations hung (interactive?)" if timed_out
              else f"CLI failed to run: {errors[0]}")
    print(json.dumps({"status": "failed", "errors": errors[:6], "detail": detail, "runs": runs}))


if __name__ == "__main__":
    main()
