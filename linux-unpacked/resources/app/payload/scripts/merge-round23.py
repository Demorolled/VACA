#!/usr/bin/env python3
"""
merge-round23.py — combine the R23 segments into the training dataset
=====================================================================
Segments (in priority order, dedupe keeps the first occurrence):
  1. training/cloud/round23-reasoning-all.jsonl     (hand-authored reasoning)
  2. training/cloud/round23-bible-code.jsonl        (bible-reference code)
  3. training/cloud/round22-app-building-expanded-train.jsonl (continuity)

Writes round23-{all,train,val}.jsonl (90/10, seed 42).
Usage: python3 scripts/merge-round23.py [--no-r22]
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud"
SEED = 42


def load(path: Path):
    rows = []
    if path.exists():
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def key(r):
    return hashlib.sha1((r.get("instruction", "") + r.get("output", "")).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-r22", action="store_true", help="skip the R22 continuity segment")
    args = ap.parse_args()

    segments = [
        ("round23-reasoning-all.jsonl", "reasoning"),
        ("round23-bible-code.jsonl", "bible"),
        (None if args.no_r22 else "round22-app-building-expanded-train.jsonl", "r22"),
    ]

    seen = set()
    merged = []
    counts = {}
    for fname, label in segments:
        if fname is None:
            continue
        n = 0
        for r in load(OUT / fname):
            k = key(r)
            if k in seen:
                continue
            seen.add(k)
            r["source"] = r.get("source", label)
            merged.append(r)
            n += 1
        counts[label] = n
        print(f"  {label:10s}: +{n} rows")

    rng = random.Random(SEED)
    rng.shuffle(merged)
    split = int(len(merged) * 0.9)
    train, val = merged[:split], merged[split:]

    for name, rows in [("all", merged), ("train", train), ("val", val)]:
        with (OUT / f"round23-{name}.jsonl").open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ round23: {len(merged)} rows (train {len(train)} / val {len(val)})")
    print("   segments:", counts)


if __name__ == "__main__":
    main()
