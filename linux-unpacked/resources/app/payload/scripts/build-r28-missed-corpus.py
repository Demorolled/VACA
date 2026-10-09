#!/usr/bin/env python3
"""
build-r28-missed-corpus.py — the R28 Kaggle corpus = MISSED TRAINING ONLY.

The 14B R20 was last trained through R18-20 (Aug 17). Rounds 21-25 produced
training/cloud/round25/all.jsonl (2,769 rows) the 14B has never seen. This
corpus is JUST that missed data — deliberately EXCLUDING any 27B-distilled
rows (round28-distill-27b.jsonl), per the user's request for the missed-only
Kaggle catch-up.

Normalizes to {instruction, input, output, source}, dedupes, shuffles seed 42,
90/10 train/val. Output is the Kaggle dataset source dir.

Usage:
  python3 scripts/build-r28-missed-corpus.py
Output:
  training/cloud/kaggle-r28/train.jsonl
  training/cloud/kaggle-r28/val.jsonl
  training/cloud/kaggle-r28/dataset_meta.json
"""
import hashlib
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "training" / "cloud" / "round25" / "all.jsonl"   # the missed R21-25 rows
OUT = ROOT / "training" / "cloud" / "kaggle-r28"


def key(r):
    return hashlib.sha1((r.get("instruction", "") + "\x00" + str(r.get("output", ""))).encode()).hexdigest()


def normalize(r):
    instruction = (r.get("instruction") or "").strip()
    inp = (r.get("input") or "").strip()
    output = (r.get("output") or "").strip()
    if not output or len(output) < 10:
        return None
    return {"instruction": instruction, "input": inp, "output": output,
            "source": r.get("source", "r28:missed")}


def main():
    if not SRC.exists():
        raise SystemExit(f"❌ {SRC} missing — no missed corpus to build")
    src_rows = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    print(f"source: {len(src_rows)} rows from {SRC.name}")

    seen, merged = set(), []
    dropped = 0
    for r in src_rows:
        row = normalize(r)
        if row is None:
            dropped += 1
            continue
        k = key(row)
        if k in seen:
            continue
        seen.add(k)
        merged.append(row)
    print(f"  normalized {len(merged)} rows (dropped {dropped} no-output)")

    rng = random.Random(42)
    rng.shuffle(merged)
    split = int(len(merged) * 0.9)
    train, val = merged[:split], merged[split:]

    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in [("train", train), ("val", val)]:
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "round": 28,
        "purpose": "14B missed-training catch-up (R21-25 only, NO 27B-distilled rows)",
        "total": len(merged), "train": len(train), "val": len(val),
        "split_seed": 42,
        "source": str(SRC),
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (OUT / "dataset_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n✅ R28 missed corpus: {len(merged)} rows (train {len(train)} / val {len(val)})")
    print(f"   → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())