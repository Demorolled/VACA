#!/usr/bin/env python3
"""
Auto-cleanup for the VACA training pipeline.

Every QLoRA round stacks ~15 GB of full-precision safetensors exports plus
several GGUF quantizations in training/cloud/out/roundN-* and
training/gui_trainer/models*. Without cleanup the project balloons (the
round-6 run alone left 99 GB; this script is what prevents round 7+ from
stacking another 40-90 GB).

Retention policy (matches the manual cleanup):
  KEEP:
    - training/cloud/out/<newest>-adapter/   (the LoRA adapter — tiny, the
      actual training output, needed for future merges)
    - training/cloud/out/<newest>-gguf/      (one F16 GGUF as re-quant source)
    - EVERYTHING in models/                  (the deployed model + any stock
      files the user keeps there) — never touched
  DELETE (superseded intermediates of ANY round, newest included once the
  GGUF export + deploy have happened):
    - roundN-merged/, roundN-export/, roundN-q4_0-export/   (safetensors,
      ~15 GB each — the merged model in full precision)
    - roundN-export_gguf/, roundN-q4_0-export_gguf/          (duplicate GGUF
      quantizations — the deployed q4_k_m in models/ supersedes them)
    - training/gui_trainer/models/                           (safetensors)
    - training/gui_trainer/models_gguf/                      (GGUF copies)

SAFETY:
  - Dry-run by default: prints what WOULD be deleted, deletes nothing.
    Pass --apply to actually delete.
  - Never deletes: the adapter dir, anything in models/, or a file currently
    serving DSpark (parsed from scripts/dspark-target.env when present).
  - Reports freed bytes so the operator sees the win.

Usage:
  python3 scripts/cleanup-round-artifacts.py            # dry run (default)
  python3 scripts/cleanup-round-artifacts.py --apply    # actually delete
  python3 scripts/cleanup-round-artifacts.py --older-only  # only rounds < newest
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOUD_OUT = ROOT / "training" / "cloud" / "out"
GUI_MODELS = ROOT / "training" / "gui_trainer" / "models"
GUI_MODELS_GGUF = ROOT / "training" / "gui_trainer" / "models_gguf"
MODELS_DIR = ROOT / "models"
TARGET_ENV = ROOT / "scripts" / "dspark-target.env"

# What we DELETE: safetensors exports + duplicate quantizations. What we keep
# per round: adapter/ (LoRA) and -gguf/ (one F16 source).
DELETE_SUFFIXES = (
    "-merged",
    "-export",
    "-q4_0-export",
    "-export_gguf",
    "-q4_0-export_gguf",
)
KEEP_SUFFIXES = ("-adapter", "-gguf")


def parse_round_dir(name: str):
    """Return (round_number, suffix) for training/cloud/out/roundN-* names."""
    m = re.match(r"^round(\d+)(-.*)$", name)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def plan_cloud_cleanup(older_only=False):
    """Compute deletions in training/cloud/out. Returns list of Paths."""
    if not CLOUD_OUT.is_dir():
        return []
    rounds = []
    for child in CLOUD_OUT.iterdir():
        parsed = parse_round_dir(child.name)
        if parsed:
            rounds.append((parsed[0], parsed[1], child))
    if not rounds:
        return []
    newest = max(r[0] for r in rounds)
    # One F16 re-quant source must survive even if the newest round's F16
    # export failed: keep the newest -gguf across ALL rounds.
    gguf_dirs = [p for rnum, suffix, p in rounds if suffix == "-gguf"]
    keep_gguf = set()
    if gguf_dirs:
        keep_gguf.add(max(gguf_dirs, key=lambda p: p.stat().st_mtime))
    deletions = []
    for rnum, suffix, path in rounds:
        # Older rounds: the whole dir goes (its adapter/gguf are superseded).
        if rnum < newest:
            if path in keep_gguf:
                continue  # but keep the last surviving F16 source
            deletions.append(path)
            continue
        # Newest round: keep adapter/ + one F16 gguf/. Drop the safetensors
        # exports and duplicate quantizations (the deploy already moved the
        # GGUF into models/). With --older-only, keep even those until the
        # NEXT round arrives (operator may still be inspecting them).
        if older_only:
            continue
        if any(suffix.startswith(s) for s in DELETE_SUFFIXES):
            deletions.append(path)
    return deletions


def plan_gui_cleanup(older_only=False):
    """training/gui_trainer/models + models_gguf are superseded exports."""
    # Never touch the trainer's live output dirs while a QLoRA run is active.
    # FAIL-SAFE: if we cannot confirm training is NOT running (pgrep missing,
    # subprocess error), stand down and delete nothing — uncertainty means
    # don't delete, for a deletion tool.
    import subprocess
    try:
        training = subprocess.run(
            ["pgrep", "-f", "launch-qlora"], capture_output=True, text=True
        ).returncode == 0
    except Exception:
        return []
    if training:
        return []
    # --older-only keeps the newest round's outputs for inspection — that
    # includes the GUI trainer copies, so skip them too for consistency.
    if older_only:
        return []
    deletions = []
    for d in (GUI_MODELS, GUI_MODELS_GGUF):
        if d.is_dir():
            # Guard against a trainer mid-write: require no .safetensors/.gguf
            # modified in the last hour before deleting.
            recent = any(
                (p.stat().st_mtime > __import__("time").time() - 3600)
                for p in d.rglob("*")
                if p.is_file() and p.suffix in (".safetensors", ".gguf")
            )
            if not recent:
                deletions.append(d)
    return deletions


def plan_models_cleanup():
    """models/ is never auto-deleted — return []. (Guarded for future use.)"""
    return []


def live_targets() -> set:
    """Files DSpark currently serves (from dspark-target.env) — never delete."""
    targets = set()
    if TARGET_ENV.is_file():
        for line in TARGET_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("DSPARK_TARGET="):
                tgt = line.split("=", 1)[1].strip().strip('"\'')
                if tgt:
                    targets.add(Path(tgt).resolve())
    return targets


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is a dry run)")
    ap.add_argument("--older-only", action="store_true",
                    help="only delete rounds older than the newest (keep the "
                         "newest round's safetensors too)")
    args = ap.parse_args()

    live = live_targets()
    deletions = (plan_cloud_cleanup(older_only=args.older_only)
                 + plan_gui_cleanup(older_only=args.older_only)
                 + plan_models_cleanup())

    # Safety: never delete a path that resolves to a live-serving file/dir.
    safe = []
    for d in deletions:
        resolved = d.resolve()
        if any(resolved == t or resolved in t.parents for t in live):
            print(f"  SKIP (live target): {d}")
            continue
        safe.append(d)

    if not safe:
        print("Nothing to clean — training/cloud/out has no superseded round "
              "artifacts (or they were already removed).")
        return 0

    total = sum(dir_size(d) for d in safe)
    print(f"Cleanup plan: {len(safe)} path(s), {total / 2**30:.1f} GB")
    for d in sorted(safe, key=str):
        print(f"  - {d}")

    if not args.apply:
        print("\nDry run — nothing deleted. Re-run with --apply to execute.")
        return 0

    freed = 0
    for d in safe:
        sz = dir_size(d)
        shutil.rmtree(d, ignore_errors=True)
        freed += sz
        print(f"  deleted {d} ({sz / 2**30:.1f} GB)")
    print(f"\nFreed {freed / 2**30:.1f} GB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
