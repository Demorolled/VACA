#!/usr/bin/env python3
"""
clean-puzzle-dpo.py — drop no-signal DPO rows from the puzzle trainer's output.
================================================================================
The DPO writer emits one row per wrong pick: chosen = the CORRECT node chunk,
rejected = what the model actually picked. When the fake node differed from the
correct chunk only by whitespace/a trailing newline, chosen == rejected after
strip — the pair carries no learning signal. This filters those out.

Usage:
  python3 scripts/clean-puzzle-dpo.py [--in <dpo.jsonl>] [--out <clean.jsonl>]

Defaults read the live puzzle-r30 out dir and write a snapshot next to it.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "puzzle-rag-trainer" / "training" / "cloud" / "puzzle-r30" / "dpo-puzzle-r30.jsonl"
DEFAULT_OUT = ROOT / "training" / "cloud" / "puzzle-r30" / "dpo-puzzle-r30-clean.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    kept = []
    dropped = 0
    for line in args.inp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        chosen = (r.get("chosen") or "").strip()
        rejected = (r.get("rejected") or "").strip()
        if not chosen or not rejected:
            dropped += 1
            continue
        if chosen == rejected:
            dropped += 1
            continue
        kept.append(r)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")

    print(f"DPO: {len(kept)} kept, {dropped} dropped (no-signal) -> {args.out}")


if __name__ == "__main__":
    main()
