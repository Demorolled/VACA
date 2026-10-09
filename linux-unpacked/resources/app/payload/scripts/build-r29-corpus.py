#!/usr/bin/env python3
"""
build-r29-corpus.py — R29 continue-training corpus (EVERYTHING still untrained).

The 14B is about to continue-training on Kaggle for 26h starting from the R28
adapter. This compiles every pool the R28 round did NOT train on (verified by
instruction-hash overlap with round28-train.jsonl):

  * sky1/                – 4,750+250 Sky-T1 reasoning rows (100% new)
  * kaggle-combined/     – 1,408 rows (819 new: round22/library/round23/rag)
  * round23-all.jsonl    – ~616 new
  * round24-all.jsonl    – ~616 new
  * round22-app-building-expanded-train.jsonl – ~216 new
  * gui-combined-all.jsonl                    – ~340 new
  * library-distilled/*  – 440 rows (all new)
  * rag-library, operator fixes, micro-orpo, verified-gen, claim-fix,
    vaca-build-fixes, live conversations (monitor) — small curated sets

Dedupes on (instruction, output-prefix) hash across sources AND drops anything
already seen in round28-train.jsonl. 95/5 seeded train/val split.

Output:
  training/cloud/round29/train.jsonl   (rows: {instruction,input,output,source,category})
  training/cloud/round29/val.jsonl
  training/cloud/round29/corpus.json   (discovery marker + row counts)
  training/cloud/round29.meta.json
"""
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "round29"
R28_TRAIN = ROOT / "training" / "cloud" / "round28-train.jsonl"

SOURCES = [
    ("sky1", ROOT / "training/cloud/sky1/train.jsonl"),
    ("sky1-val", ROOT / "training/cloud/sky1/val.jsonl"),
    ("kaggle-combined", ROOT / "training/cloud/kaggle-combined/train.jsonl"),
    ("round23-all", ROOT / "training/cloud/round23-all.jsonl"),
    ("round24-all", ROOT / "training/cloud/round24-all.jsonl"),
    ("round22-expanded", ROOT / "training/cloud/round22-app-building-expanded-train.jsonl"),
    ("puzzle-r30", ROOT / "training/cloud/puzzle-r30/train-puzzle-r30.jsonl"),
    ("gui-combined", ROOT / "training/cloud/gui-combined-all.jsonl"),
    ("library-distilled", ROOT / "training/dataset/library-distilled"),  # glob dir
    ("rag-library", ROOT / "training/dataset/rag-library.jsonl"),
    ("operator-datasheet", ROOT / "training/operator/datasheet-fixes.jsonl"),
    ("operator-buildladder", ROOT / "training/operator/dataset/round9-buildladder.jsonl"),
    ("micro-orpo", ROOT / "training/dataset/micro-orpo-pairs.jsonl"),
    ("verified-generations", ROOT / "training/dataset/verified-generations.jsonl"),
    ("claim-fix", ROOT / "training/cloud/claim-fix-corpus.jsonl"),
    ("vaca-build-fixes", ROOT / "training/dataset/vaca-build-fixes.jsonl"),
    ("live-conversations", ROOT / "data/monitor/conversations.jsonl"),
]


def row_key(r):
    return hashlib.sha1(
        (str(r.get("instruction", "")) + "\x00" + str(r.get("output", ""))[:200]).encode()
    ).hexdigest()


def rows_of(path: Path):
    """Yield normalized {instruction,input,output,source,category} dicts."""
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out = (r.get("output") or "").strip()
            ins = (r.get("instruction") or r.get("problem") or "").strip()
            if not out or len(out) < 10 or not ins:
                continue
            inp = (r.get("input") or "").strip()
            cat = r.get("category", r.get("source", "raw"))
            yield {"instruction": ins, "input": inp, "output": out,
                   "source": r.get("source", "raw"), "category": cat}


def main():
    # What R28 already trained on (drop these).
    seen_r28 = set()
    if R28_TRAIN.exists():
        for r in rows_of(R28_TRAIN):
            seen_r28.add(row_key(r))
    print(f"R28 trained keys: {len(seen_r28)}")

    OUT.mkdir(parents=True, exist_ok=True)
    kept = Counter()
    dropped = Counter()
    total = Counter()
    seen = set()

    rows = []
    for label, path in SOURCES:
        if not path.exists():
            print(f"  ⚠️  skip {label}: {path} missing")
            continue
        n = 0
        for r in rows_of(path):
            n += 1
            total[label] += 1
            k = row_key(r)
            if k in seen_r28:
                dropped["r28-dup"] += 1
                continue
            if k in seen:
                dropped["dup"] += 1
                continue
            seen.add(k)
            rows.append({**r, "source": f"r29:{label}"})
            kept[label] += 1
        print(f"  {label:22s} total={n:6d} kept={kept[label]:5d}")

    print(f"\nTOTAL kept: {len(rows)} (from {sum(total.values())} raw rows)")

    random.Random(42).shuffle(rows)
    split = int(len(rows) * 0.95)
    train, val = rows[:split], rows[split:]

    with (OUT / "train.jsonl").open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r) + "\n")
    with (OUT / "val.jsonl").open("w", encoding="utf-8") as f:
        for r in val:
            f.write(json.dumps(r) + "\n")

    corpus = {
        "round": 29,
        "purpose": "26h continue-training from the R28 adapter — all untrained pools",
        "total_rows": len(rows),
        "train_rows": len(train),
        "val_rows": len(val),
        "dropped": dict(dropped),
        "by_source": dict(kept),
    }
    (OUT / "corpus.json").write_text(json.dumps(corpus, indent=2))
    meta = {
        "generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .isoformat().replace("+00:00", "Z"),
        "round": 29,
        "base_model": "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored",
        "start_adapter": "R28 (training/cloud/out/round28-14b/final)",
        "**corpus**": corpus,
    }
    (OUT / ".." / "round29.meta.json").resolve().write_text(json.dumps(meta, indent=2))
    print(f"\n✅ {len(train)} train / {len(val)} val → {OUT}")
    print("   (corpus.json marker written — Kaggle kernel discovers this dir)")


if __name__ == "__main__":
    main()