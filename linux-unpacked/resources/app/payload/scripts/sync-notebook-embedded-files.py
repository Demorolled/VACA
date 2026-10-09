#!/usr/bin/env python3
"""
sync-notebook-embedded-files.py — re-embed the CURRENT repo source into the
`%%writefile <name>` cells of the Colab/Kaggle training notebooks.

Why: `scripts/validate-cloud-notebooks.py` byte-matches every notebook's
embedded `%%writefile` body against the repo source file (so a stale trainer
can't ride along), and `scripts/check-training.sh` red-gates `npm run build` on
that check. When the repo source is edited (e.g. `train_round1.py`) the
historical notebooks drift and the gate fails even though nothing in the
notebook is broken. This script performs the sanctioned fix: rewrite those cells
to match the current source, leaving every other cell untouched.

Idempotent: cells already matching the repo source are left byte-identical, so
re-running produces no diff.

Usage:
  python3 scripts/sync-notebook-embedded-files.py          # rewrite stale cells
  python3 scripts/sync-notebook-embedded-files.py --check  # report only, exit 1 if stale
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIRS = [
    ROOT / "training" / "cloud" / "colab",
    ROOT / "training" / "cloud" / "kaggle",
]


def resolve_source_for(target: str):
    """Find the repo source a writefile target should match (same rule as the validator)."""
    if not target:
        return None
    for base in (ROOT / "training" / "cloud", ROOT):
        cand = base / target
        if cand.exists():
            return cand
    return None


def sync_notebook(path: Path, check_only: bool) -> int:
    nb = json.loads(path.read_text())
    changed = 0
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        lines = src.splitlines()
        if not lines or not lines[0].strip().startswith("%%writefile"):
            continue
        parts = lines[0].split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else None
        src_file = resolve_source_for(target) if target else None
        if src_file is None:
            continue
        body = "\n".join(lines[1:])
        if body.strip() == src_file.read_text().strip():
            continue
        changed += 1
        if check_only:
            print(f"  STALE {path.relative_to(ROOT)}: {target}")
            continue
        # Keep the original directive line verbatim; re-embed the file body.
        cell["source"] = [lines[0] + "\n"] + [ln + "\n" for ln in src_file.read_text().splitlines()]
    if changed and not check_only:
        path.write_text(json.dumps(nb, indent=1))
        print(f"  synced {changed} cell(s) in {path.relative_to(ROOT)}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report stale cells only; exit 1 if any")
    args = ap.parse_args()

    notebooks = []
    for d in NOTEBOOK_DIRS:
        if d.is_dir():
            notebooks.extend(sorted(d.glob("*.ipynb")))
    if not notebooks:
        print("  no notebooks found (nothing to sync)", file=sys.stderr)
        return 0

    total = 0
    for nb in notebooks:
        total += sync_notebook(nb, args.check)
    if args.check and total:
        print(f"❌ {total} stale embedded cell(s) — run without --check to fix", file=sys.stderr)
        return 1
    if not args.check:
        print(f"✅ synced {total} embedded cell(s) across {len(notebooks)} notebook(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
