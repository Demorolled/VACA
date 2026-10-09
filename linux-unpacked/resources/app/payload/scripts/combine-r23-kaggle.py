#!/usr/bin/env python3
"""
combine-r23-kaggle.py — merge ALL RAG training segments into ONE Kaggle dataset
===============================================================================
Sources (in priority order; dedupe keeps first occurrence):
  1. training/dataset/rag-distilled-*.jsonl           (RAG teacher distillation)
  2. training/dataset/library-distilled/*.jsonl        (bible/library distillation)
  3. training/cloud/round21-app-building-all.jsonl     (R21 app-building)
  4. training/cloud/round22-app-building-expanded-all.jsonl  (R22 expanded)
  5. training/cloud/round23-all.jsonl                  (R23: reasoning + bible-code + R22 continuity)

Normalizes every row to {instruction, input, output, source}, dedupes on
sha1(instruction+output), shuffles with seed 42, writes 90/10 train/val.

Usage (ON THE AGENT):
  python3 scripts/combine-r23-kaggle.py
Output:
  training/cloud/kaggle-combined/train.jsonl
  training/cloud/kaggle-combined/val.jsonl
  training/cloud/kaggle-combined/dataset_meta.json
"""
import glob
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "kaggle-combined"

SEGMENTS = [
    ("rag-distilled", sorted(glob.glob(str(ROOT / "training/dataset/rag-distilled-*.jsonl")))),
    ("library-distilled", sorted(glob.glob(str(ROOT / "training/dataset/library-distilled/*.jsonl")))),
    ("round21", [ROOT / "training/cloud/round21-app-building-all.jsonl"]),
    ("round22", [ROOT / "training/cloud/round22-app-building-expanded-all.jsonl"]),
    ("round23", [ROOT / "training/cloud/round23-all.jsonl"]),
]


def load(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def key(r):
    return hashlib.sha1((r.get("instruction", "") + r.get("output", "")).encode()).hexdigest()


def normalize(r, source):
    instruction = (r.get("instruction") or "").strip()
    inp = (r.get("input") or "").strip()
    output = (r.get("output") or "").strip()
    if not output or len(output) < 10:
        return None
    return {"instruction": instruction, "input": inp, "output": output, "source": source}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set()
    merged = []
    counts = {}
    for label, paths in SEGMENTS:
        n = 0
        for p in paths:
            for r in load(Path(p)):
                row = normalize(r, label)
                if row is None:
                    continue
                k = key(row)
                if k in seen:
                    continue
                seen.add(k)
                merged.append(row)
                n += 1
        counts[label] = n
        print(f"  {label:18s}: +{n} rows")

    rng = random.Random(42)
    rng.shuffle(merged)
    split = int(len(merged) * 0.9)
    train, val = merged[:split], merged[split:]

    for name, rows in [("train", train), ("val", val)]:
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "total": len(merged), "train": len(train), "val": len(val),
        "segments": counts, "split_seed": 42, "created": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (OUT / "dataset_meta.json").write_text(json.dumps(meta, indent=2))

    print(f"\n✅ combined: {len(merged)} rows (train {len(train)} / val {len(val)})")
    print("   segments:", counts)
    print(f"   → {OUT}")


if __name__ == "__main__":
    main()
