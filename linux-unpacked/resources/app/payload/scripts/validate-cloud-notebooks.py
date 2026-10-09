#!/usr/bin/env python3
"""
validate-cloud-notebooks.py — compile-check every code cell of the Colab and
Kaggle notebooks so escaping/typo bugs in generated cells can never ship again.

Background (2026-08-01): build-colab-notebook.py emitted a Step-2 cell with an
unescaped apostrophe inside a single-quoted string:

    print('(If unsloth fails to import, Colab's Python may be too new — switch the runtime to Python 3.12.)')

The whole cell — including `!pip install unsloth ...` — was a SyntaxError and
never ran, so every Colab session died at Step 2. This validator makes that
class of bug impossible to ship silently:

  • every code cell of every generated notebook is compile-checked (with shell
    lines and cell/line magics stripped);
  • `%%writefile` embedded scripts are additionally compared byte-for-byte
    against the repo source file, so a stale trainer can't ride along either;
  • `--self-test` proves the checker actually catches the original bug.

Usage:
  python3 scripts/validate-cloud-notebooks.py                      # colab/ + kaggle/ dirs
  python3 scripts/validate-cloud-notebooks.py --notebooks path...  # specific notebooks
  python3 scripts/validate-cloud-notebooks.py --no-disk-match      # skip byte-match vs repo
  python3 scripts/validate-cloud-notebooks.py --self-test          # regression proof
  python3 scripts/validate-cloud-notebooks.py --quiet              # only print failures

Exit code: 0 = all cells valid · 1 = any cell fails.
Wired into scripts/check-training.sh so every pipeline build runs it.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = [
    ROOT / "training" / "cloud" / "colab",
    ROOT / "training" / "cloud" / "kaggle",
]


def compile_cell(code: str, name: str):
    """Compile a block of Python. Returns (ok, SyntaxError-or-None)."""
    try:
        compile(code, name, "exec")
        return True, None
    except SyntaxError as e:
        return False, e


def strip_shell_and_magics(src: str) -> str:
    """Return the Python portion of a notebook cell.

    - Lines starting with `!` (shell) are dropped, along with any backslash
      continuation lines that belong to the same shell command.
    - Cell magics (`%%...`) and line magics (`%...`) are dropped.
    """
    lines = src.splitlines()
    out = []
    in_shell = False
    for line in lines:
        stripped = line.strip()
        if in_shell:
            if not stripped.endswith("\\"):
                in_shell = False
            continue
        if stripped.startswith("!"):
            in_shell = stripped.endswith("\\")
            continue
        if stripped.startswith("%"):
            continue
        out.append(line)
    return "\n".join(out)


def extract_writefile(src: str):
    """If the cell is a `%%writefile <name>` cell, return (name, body)."""
    lines = src.splitlines()
    if not lines:
        return None, None
    first = lines[0].strip()
    if first.startswith("%%writefile"):
        parts = first.split(None, 1)
        name = parts[1].strip() if len(parts) > 1 else None
        return name, "\n".join(lines[1:])
    return None, None


def resolve_source_for(target: str) -> Optional[Path]:
    """Find the repo source file a writefile target should match."""
    if not target:
        return None
    for base in (ROOT / "training" / "cloud", ROOT):
        cand = base / target
        if cand.exists():
            return cand
    return None


def check_notebook(path: Path, quiet: bool = False, disk_match: bool = True):
    """Validate a single notebook. Returns (all_ok, problems)."""
    problems = []
    try:
        nb = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return False, [f"cannot read notebook: {e}"]

    cells = nb.get("cells", [])
    if not quiet:
        print(f"  {path.name} ({len(cells)} cells)")

    all_ok = True
    for idx, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))

        # %%writefile embedded script: compile body + byte-match repo source
        target, body = extract_writefile(src)
        if target:
            ok, err = compile_cell(body, f"{path.name}#cell{idx}(writefile {target})")
            status = []
            if not ok:
                all_ok = False
                status.append(f"SYNTAX ERROR: {err}")
            if disk_match:
                src_file = resolve_source_for(target)
                if src_file is not None and body.strip() != src_file.read_text().strip():
                    all_ok = False
                    status.append(
                        f"STALE: embedded {target} differs from "
                        f"{src_file.relative_to(ROOT)}"
                    )
            if status:
                problems.append(f"cell {idx} ({target}): {'; '.join(status)}")
            elif not quiet:
                print(f"    ✓ cell {idx}  writefile {target} (compiles, matches disk)")
            continue

        # ordinary / mixed cell: compile the Python portion
        code = strip_shell_and_magics(src)
        if not code.strip():
            # Shell-only cell: Colab !-lines are plain shell — NO f-string
            # interpolation. A literal `{LR}`/`{EPOCHS}` placeholder would be
            # passed verbatim to the shell/argparse and crash the run, so flag
            # any {UPPERCASE} placeholder in a shell cell as a hard error.
            import re as _re
            placeholders = _re.findall(r"\{[A-Z][A-Z0-9_]*\}", src)
            if placeholders:
                all_ok = False
                problems.append(
                    f"cell {idx}: shell cell contains un-interpolated "
                    f"placeholders {placeholders} (Colab !-cells are shell — "
                    f"use a Python cell with .format()/f-string instead)"
                )
            elif not quiet:
                print(f"    ✓ cell {idx}  shell-only (skipped)")
            continue
        ok, err = compile_cell(code, f"{path.name}#cell{idx}")
        if ok:
            if not quiet:
                print(f"    ✓ cell {idx}  python ({len(code.splitlines())} lines)")
        else:
            all_ok = False
            problems.append(f"cell {idx}: SYNTAX ERROR: {err}")
            lineno = getattr(err, "lineno", None)
            if lineno:
                lines = code.splitlines()
                lo = max(0, lineno - 2)
                hi = min(len(lines), lineno + 1)
                for j in range(lo, hi):
                    mark = ">>" if j == lineno - 1 else "  "
                    problems.append(f"        {mark} {j + 1}: {lines[j][:100]}")

    return all_ok, problems


def run_self_test() -> bool:
    """Prove the checker catches the original escaping bug + a stale writefile."""
    tmp = Path(tempfile.mkdtemp(prefix="vaca-nbval-"))
    ok = True
    # pytest-friendly temp dir cleanup
    try:
        ok = _run_self_test(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def _run_self_test(tmp: Path) -> bool:
    ok = True

    def make_nb(cells: list) -> dict:
        return {
            "cells": cells,
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    # 1. The original bug: unescaped apostrophe in a single-quoted string.
    bad = make_nb(
        [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "!python --version\n",
                    "print('(If unsloth fails to import, Colab's Python may be too new — switch the runtime to Python 3.12.)')\n",
                ],
            }
        ]
    )
    bad_p = tmp / "bad_escaping.ipynb"
    bad_p.write_text(json.dumps(bad))
    bad_ok, bad_problems = check_notebook(bad_p, quiet=True)
    if bad_ok:
        print("  ✗ self-test 1 (escaping bug) NOT caught!")
        ok = False
    else:
        print(f"  ✓ self-test 1 catches the escaping SyntaxError ({bad_problems[0][:80]}...)")

    # 2. A clean cell must pass.
    good = make_nb(
        [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["print(\"hello, world\")\n"],
            }
        ]
    )
    good_p = tmp / "good.ipynb"
    good_p.write_text(json.dumps(good))
    good_ok, good_problems = check_notebook(good_p, quiet=True)
    if not good_ok:
        print(f"  ✗ self-test 2 (clean cell) failed: {good_problems}")
        ok = False
    else:
        print("  ✓ self-test 2 clean cell passes")

    # 3. A stale writefile must be caught (if the repo source exists).
    src_file = resolve_source_for("train_round1.py")
    if src_file is not None:
        stale = make_nb(
            [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "%%writefile train_round1.py\n",
                        "# intentionally stale trainer body\n",
                        "print(1)\n",
                    ],
                }
            ]
        )
        stale_p = tmp / "stale_writefile.ipynb"
        stale_p.write_text(json.dumps(stale))
        stale_ok, stale_problems = check_notebook(stale_p, quiet=True)
        if stale_ok:
            print("  ✗ self-test 3 (stale writefile) NOT caught!")
            ok = False
        else:
            print(f"  ✓ self-test 3 catches the stale writefile ({stale_problems[0][:80]}...)")
    else:
        print("  - self-test 3 skipped (no repo train_round1.py to compare)")

    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notebooks", nargs="+", help="specific notebooks to validate")
    ap.add_argument("--no-disk-match", action="store_true",
                    help="skip the byte-match of %%writefile scripts vs repo source")
    ap.add_argument("--self-test", action="store_true", help="run regression self-tests")
    ap.add_argument("--quiet", action="store_true", help="only print failures")
    args = ap.parse_args()

    if args.self_test:
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    if args.notebooks:
        paths = [Path(p) for p in args.notebooks]
    else:
        paths = [p for d in DEFAULT_DIRS for p in d.glob("*.ipynb") if p.is_file()]

    if not paths:
        print("  ✗ no notebooks found")
        sys.exit(1)

    all_ok = True
    for path in sorted(paths):
        ok, problems = check_notebook(path, quiet=args.quiet,
                                      disk_match=not args.no_disk_match)
        for pr in problems:
            print(f"    ✗ {pr}")
        if not ok:
            all_ok = False
            print(f"  ❌ {path.name} FAILED")
        elif not args.quiet:
            print(f"  ✅ {path.name} OK")

    print("✅ validate-cloud-notebooks: all notebooks valid" if all_ok
          else "❌ validate-cloud-notebooks: FAILED")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
