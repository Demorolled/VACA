#!/usr/bin/env python3
"""purge-scaffold-training-rows.py — stop training the LLM to BE the scaffolder.

Why this exists
---------------
The project direction (2026-10-03) is: **VACA builds the scaffold; the LLM fills
in the code VACA asks for.** Teaching the model to invent the app's node graph,
file plan, or architecture is the approach that was measured to be a dead end
(the per-file scaffold LLM step was removed 2026-10-02; see
`runs/scaffold-ab/removed/REMOVAL.md` and `runs/GATE_NUMBERS.md`).

Some corpora still carry rows whose *instruction asks the model to design the
app* and whose *output is a scaffold/plan* rather than a source file. Those rows
teach exactly the behaviour we are removing, so they are purged here.

What is purged (generation-style rows)
--------------------------------------
| pattern                     | example instruction                                        |
|-----------------------------|------------------------------------------------------------|
| `design_arch`               | "Design the complete architecture for a URL shortener..."   |
| `decompose`                 | "Decompose a task manager app into its architectural..."    |
| `design_node_graph`         | "Design the node graph for: <goal>"                         |
| `canvas_nodes_q`            | "What nodes and wiring should the VACA canvas contain for X"|
| `app_template_q`            | "Which nodes, files, languages and database should a X app" |
| `build_me_blueprint`        | "Build me <description>" (output = a blueprint spec)        |

What is KEPT (VACA-knowledge rows)
----------------------------------
Rows that *describe VACA* rather than ask the model to produce a design are
knowledge, not scaffolding behaviour, and are deliberately left alone, e.g.
"What blueprint shape does VACA require...", "What is VACA's universal project
skeleton...", "Explain VACA's node architecture: ...". They teach the model about
the harness it is running inside — which is the thing it should take its lead
from.

Usage
-----
    python3 scripts/purge-scaffold-training-rows.py            # dry run (default)
    python3 scripts/purge-scaffold-training-rows.py --apply    # rewrite + backup

Backups are written next to the original as `<name>.pre-scaffold-purge-<ts>` so
a purge is reversible without git.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Instruction patterns that ask the MODEL to design/produce a scaffold or plan.
PURGE_PATTERNS: dict[str, re.Pattern[str]] = {
    "design_arch": re.compile(r"^Design the complete architecture for\b", re.I),
    "decompose": re.compile(r"^Decompose .* into its architectural\b", re.I),
    "design_node_graph": re.compile(r"^Design the node graph for\b", re.I),
    "canvas_nodes_q": re.compile(r"^What nodes and wiring should the VACA canvas contain\b", re.I),
    "app_template_q": re.compile(r"^Which nodes, files, languages and database should\b", re.I),
    "build_me_blueprint": re.compile(r"^Build me\b", re.I),
}

# Files scanned. Relative to the repo root.
CORPORA = [
    "kaggle_upload/train.jsonl",
    "kaggle_upload/val.jsonl",
    "training/selfplay/corpus/vaca-domain.jsonl",
    "training/selfplay/corpus/r1/train.jsonl",
    "training/selfplay/corpus/r1/val.jsonl",
]
# The campaign50 dataset zip is a packaged copy of the same material.
CAMPAIGN_ZIP = "training/cloud/campaign50-dataset.zip"


def classify(instruction: str) -> str | None:
    ins = (instruction or "").strip()
    for name, pat in PURGE_PATTERNS.items():
        if pat.search(ins):
            return name
    return None


def scan_lines(name: str, lines: list[str]) -> tuple[dict[str, int], int, list[str]]:
    """Return (per-pattern counts, total rows, kept lines)."""
    counts: dict[str, int] = {}
    kept: list[str] = []
    total = 0
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except json.JSONDecodeError:
            kept.append(raw)
            continue
        total += 1
        hit = classify(rec.get("instruction", ""))
        if hit:
            counts[hit] = counts.get(hit, 0) + 1
        else:
            kept.append(raw)
    return counts, total, kept


def purge_file(path: Path, apply: bool, ts: str) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    counts, total, kept = scan_lines(path.name, lines)
    removed = sum(counts.values())
    if apply and removed:
        shutil.copy2(path, path.with_name(path.name + f".pre-scaffold-purge-{ts}"))
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(ROOT)), "total": total,
            "removed": removed, "kept": total - removed, "counts": counts}


def purge_zip(path: Path, apply: bool, ts: str) -> dict | None:
    if not path.exists():
        return None
    results = []
    with zipfile.ZipFile(path) as z:
        members = z.namelist()
        rebuilt: dict[str, bytes] = {}
        total = removed = 0
        counts: dict[str, int] = {}
        for name in members:
            data = z.read(name).decode("utf-8").splitlines()
            c, t, kept = scan_lines(name, data)
            total += t
            removed += sum(c.values())
            for k, v in c.items():
                counts[k] = counts.get(k, 0) + v
            rebuilt[name] = ("\n".join(kept) + "\n").encode("utf-8")
    if apply and removed:
        shutil.copy2(path, path.with_name(path.name + f".pre-scaffold-purge-{ts}"))
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, blob in rebuilt.items():
                z.writestr(name, blob)
    results.append({"path": str(path.relative_to(ROOT)), "total": total,
                    "removed": removed, "kept": total - removed, "counts": counts})
    return results[0]


def self_test() -> int:
    """Prove the classifier catches every scaffold form and spares VACA knowledge.

    No pytest dependency — matches the repo's stdlib-only test convention
    (scripts/test-benchmark-dspark.py). Run: python3 <this> --self-test
    """
    should_purge = [
        "Design the complete architecture for a URL shortener. List every file.",
        "Decompose a task manager app into its architectural components.",
        "Design the node graph for: Task Management App",
        "What nodes and wiring should the VACA canvas contain for `Blog`?",
        "Which nodes, files, languages and database should a `CLI Tool` app in VACA use?",
        "Build me Tic-Tac-Toe with unbeatable minimax AI",
    ]
    should_keep = [
        "What blueprint shape does VACA require, and what is the wiring for a `todo` app?",
        "What is VACA's universal project skeleton (files every generated app gets)?",
        "Explain VACA's node architecture: Core Loop",
        "What nodes, files, languages and database does VACA's `CLI Tool` app template define?",
        "Generate the COMPLETE file 'src/todo.ts' for the multi-file app above.",
        "Design the database schema for a notes app",  # not a VACA-scaffold row
    ]
    fails = []
    for ins in should_purge:
        if classify(ins) is None:
            fails.append(f"MISSED (should purge): {ins!r}")
    for ins in should_keep:
        if classify(ins) is not None:
            fails.append(f"FALSE POSITIVE (should keep): {ins!r}")
    if fails:
        for f in fails:
            print(f"  ✗ {f}")
        print(f"[purge] self-test FAILED ({len(fails)} case(s))")
        return 1
    print(f"[purge] self-test OK — {len(should_purge)} purged, {len(should_keep)} kept")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="rewrite the corpora (default is a dry run)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the classifier self-test and exit")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    ts = time.strftime("%Y%m%d-%H%M%S")

    print(f"[purge] mode={'APPLY' if args.apply else 'DRY-RUN'} patterns={list(PURGE_PATTERNS)}")
    grand_removed = grand_total = 0
    for rel in CORPORA:
        p = ROOT / rel
        if not p.exists():
            continue
        r = purge_file(p, args.apply, ts)
        grand_removed += r["removed"]
        grand_total += r["total"]
        if r["removed"]:
            print(f"  {r['path']}: removed {r['removed']}/{r['total']} -> " +
                  ", ".join(f"{k}={v}" for k, v in sorted(r["counts"].items())))
        else:
            print(f"  {r['path']}: nothing to remove ({r['total']} rows)")

    zr = purge_zip(ROOT / CAMPAIGN_ZIP, args.apply, ts)
    if zr:
        grand_removed += zr["removed"]
        grand_total += zr["total"]
        if zr["removed"]:
            print(f"  {zr['path']}: removed {zr['removed']}/{zr['total']} -> " +
                  ", ".join(f"{k}={v}" for k, v in sorted(zr["counts"].items())))
        else:
            print(f"  {zr['path']}: nothing to remove ({zr['total']} rows)")

    print(f"[purge] {'removed' if args.apply else 'would remove'} "
          f"{grand_removed}/{grand_total} rows across the corpora")
    if not args.apply and grand_removed:
        print("[purge] re-run with --apply to rewrite (backups are written first)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
