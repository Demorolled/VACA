#!/usr/bin/env python3
"""
Build the Round-19 corpus for the Qwen2.5-Coder-14B-Instruct-Uncensored fine-tune.

CONTINUATION round (resumes from the R18 LoRA). Same source mix as R18 plus the
new targeted data from the R18->R19 gap:
  - repair-pairs now includes the 3 MULTI-FILE repair rows (todo_list
    input-handler / data-store / task-store — the import-based multi-file style
    that fixes the scope-leak / invented-member failure classes).
  - verified-generations includes today's converged blueprint captures.

KAGGLE QUOTA CAP: the weekly quota has ~10h left and R18 took ~6.5-7h for
2,117 rows / 1 epoch. R19 therefore DEFAULTS to --max-rows 1900 (trim keeps
ALL code rows first: R16 611 + ladder 155 + verified ~100 + repair-pairs 9,
then emotion fills the remainder ~1,025) → estimated ~6-6.5h, comfortably
under the quota with margin. Training: resume R18 adapter, LR 3e-5, 1 epoch.

Deduplicates by (instruction, output) hash; keeps the FIRST occurrence from
the higher-priority source. Writes training/cloud/round19-train.jsonl + a meta
file with the per-source breakdown (same shape as round18.meta.json).

Usage:
  python3 scripts/build-r19-corpus.py                    # capped at 1,900 rows
  python3 scripts/build-r19-corpus.py --max-rows 0       # full corpus (no cap)
"""
import argparse
import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "round19-train.jsonl"
META = ROOT / "training" / "cloud" / "round19.meta.json"

SOURCES = [
    # (label, path, filter_source_prefixes)  — None = take every row
    ("round16-antifence-all", ROOT / "training" / "cloud" / "round16-antifence-all.jsonl", None),
    ("ladder-r1", ROOT / "training" / "cloud" / "ladder-r1-train.jsonl", None),
    ("round7-emotion", ROOT / "dataset" / "round7-emotion.jsonl", None),
    ("verified-generations", ROOT / "training" / "dataset" / "verified-generations.jsonl", ("blueprint-verified", "verified-generation")),
    ("repair-pairs", ROOT / "training" / "dataset" / "repair-pairs.jsonl", None),
]

# Source priority for TRIM mode (code knowledge first, emotion fills remainder)
TRIM_PRIORITY = [
    "round16-antifence-all",
    "ladder-r1",
    "verified-generations",
    "repair-pairs",
    "round7-emotion",
]


def row_hash(r):
    return hashlib.sha256(
        (str(r.get("instruction", "")) + "\x00" + str(r.get("output", ""))).encode()
    ).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Build R19 corpus (capped for the Kaggle 10h quota)")
    ap.add_argument("--max-rows", type=int, default=1900,
                    help="Cap total rows (default 1900 for <10h training; 0 = full corpus)")
    args = ap.parse_args()
    max_rows = args.max_rows

    src_map = {label: (path, prefixes) for label, path, prefixes in SOURCES}
    order = TRIM_PRIORITY if max_rows else [s[0] for s in SOURCES]

    seen = set()
    kept = Counter()
    total = Counter()
    with open(OUT, "w", encoding="utf-8") as f:
        for label in order:
            path, prefixes = src_map[label]
            if not path.exists():
                print(f"  ⚠️  skip {label}: {path} missing")
                continue
            for line in open(path, encoding="utf-8"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prefixes and not any(str(r.get("source", "")).startswith(p) for p in prefixes):
                    continue
                total[label] += 1
                h = row_hash(r)
                if h in seen:
                    continue
                seen.add(h)
                if max_rows and sum(kept.values()) >= max_rows:
                    break
                kept[label] += 1
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if max_rows and sum(kept.values()) >= max_rows:
                print(f"  ⏹  cap of {max_rows} reached during {label}")
                break

    total_rows = sum(kept.values())
    meta = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "round": 19,
        "base_model": "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored",
        "resumes_from": "round18",
        "purpose": (
            "Continuation of R18 (14B coder base): R18 sources PLUS the new "
            "multi-file repair-pairs (3 import-based todo_list rows) and "
            "today's converged blueprint captures. Capped at 1900 rows so the "
            "kernel fits the remaining ~10h weekly Kaggle quota (~6-6.5h est); "
            "trim keeps ALL code rows (R16+ladder+verified+repair-pairs) and "
            "fills the remainder with the round7-emotion register. "
            "Train: resume R18 adapter, LR 3e-5, 1 epoch, seq 3072."
        ),
        "max_rows": max_rows if max_rows else None,
        "total_rows": total_rows,
        "by_source": {k: v for k, v in kept.items()},
        "per_source": {k: v for k, v in total.items()},
    }
    META.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"\nWrote {total_rows} rows -> {OUT}")
    print(f"Meta -> {META}")
    for k in kept:
        print(f"  {k}: kept {kept[k]} of {total[k]}")


if __name__ == "__main__":
    main()
