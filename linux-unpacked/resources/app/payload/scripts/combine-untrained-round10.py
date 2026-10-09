#!/usr/bin/env python3
"""
combine-untrained-round10.py — compile every untrained row into one Kaggle set
================================================================================
Scan (2026-08-09) found three datasets with rows NOT in the trained union
(base train/val + rounds 2-7 + gui-combined-all):

  new training data set/bible-patterns-new.jsonl   573 new rows (of 1,079; 506
                                                   already trained in round 9)
  training/dataset/round8-code.jsonl               399 rows (round 8 never ran)
  training/dataset/verified-generations.jsonl      137 new rows (97% new)

Outputs (deterministic, seed 42, 90/10):
  training/cloud/round10-untrained-all.jsonl   (merged + deduped)
  training/cloud/round10-train.jsonl
  training/cloud/round10-val.jsonl
  training/cloud/round10-untrained.meta.json

Usage:
  python3 scripts/combine-untrained-round10.py
"""

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud"
SEED = 42

SOURCES = [
    ROOT.parent / "new training data set" / "bible-patterns-new.jsonl",
    ROOT / "training" / "dataset" / "round8-code.jsonl",
    ROOT / "training" / "dataset" / "verified-generations.jsonl",
]

# Everything already trained (base train/val + rounds 2-7 + gui-combined-all).
# Rows matching these are excluded so round 10 trains ONLY new signal.
TRAINED_UNION = [
    ROOT / "training" / "dataset" / "train.jsonl",
    ROOT / "training" / "dataset" / "val.jsonl",
    ROOT / "training" / "dataset" / "round2-mixed.jsonl",
    ROOT / "training" / "dataset" / "round3-mixed.jsonl",
    ROOT / "training" / "dataset" / "round4-failures.jsonl",
    ROOT / "training" / "dataset" / "round5-blueprints.jsonl",
    ROOT / "training" / "dataset" / "round6-bible-10h.jsonl",
    ROOT / "training" / "dataset" / "round7-emotion.jsonl",
    ROOT / "training" / "cloud" / "gui-combined-all.jsonl",
]


def row_key(r: dict) -> str:
    return hashlib.md5(
        f"{r.get('instruction', '')}|{r.get('input', '')}|{r.get('output', '')}".encode()
    ).hexdigest()


def load(path: Path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  ⚠️  skip unparseable line in {path.name}")
    return rows


def main():
    print("[round10] sources:")
    # Build the already-trained key set once.
    trained_keys = set()
    for path in TRAINED_UNION:
        trained_keys |= {row_key(r) for r in load(path)}
    print(f"  trained union: {len(trained_keys)} rows (excluded from round 10)")

    merged = []
    seen = set()
    src_counts = Counter()
    for path in SOURCES:
        rows = load(path)
        added = 0
        for r in rows:
            k = row_key(r)
            if k in seen or k in trained_keys:
                continue
            seen.add(k)
            r.setdefault("source", f"round10:{path.parent.name}")
            merged.append(r)
            added += 1
        src_counts[path.name] = added
        print(f"  {path.name}: {len(rows)} rows → {added} new (not previously trained)")

    print(f"\n[round10] merged: {len(merged)} unique untrained rows")
    random.Random(SEED).shuffle(merged)
    n_val = max(1, round(len(merged) * 0.10))
    val, train = merged[:n_val], merged[n_val:]

    out_all = OUT / "round10-untrained-all.jsonl"
    out_train = OUT / "round10-train.jsonl"
    out_val = OUT / "round10-val.jsonl"
    out_meta = OUT / "round10-untrained.meta.json"

    for path, rows in [(out_all, merged), (out_train, train), (out_val, val)]:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "generated": "2026-08-09",
        "total_unique": len(merged),
        "by_source": dict(src_counts),
        "split": {"train": len(train), "val": len(val), "seed": SEED},
    }
    out_meta.write_text(json.dumps(meta, indent=2))

    print(f"[round10] all  : {out_all} ({len(merged)} rows)")
    print(f"[round10] train: {out_train} ({len(train)} rows)")
    print(f"[round10] val  : {out_val} ({len(val)} rows)")
    print(f"[round10] meta : {out_meta}")


if __name__ == "__main__":
    main()
