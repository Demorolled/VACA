#!/usr/bin/env python3
"""
build-r20-orpo-corpus.py — Round-20 ORPO corpus from the preference pairs.

Reads training/dataset/orpo-pairs.jsonl (instruction / chosen / rejected —
the model's OWN tsc-clean finals vs its OWN broken first drafts, built by
scripts/build-orpo-pairs.py from the snapshotFirstDrafts captures, #62) and
writes the Round-20 ORPO training corpus:

    training/cloud/round20-orpo-train.jsonl   (one {instruction, chosen,
                                                rejected} pair per line)
    training/cloud/round20.meta.json          (counts + dedup stats)

ORPO is preference tuning, NOT SFT: there is no {input, output} — each row
teaches the model to PREFER the converged file over the first draft for the
same instruction. The trainer consumes it via --train-type orpo.

Usage:
  python3 scripts/build-orpo-pairs.py          # first: build/refresh the pairs
  python3 scripts/build-r20-orpo-corpus.py     # then: compile the corpus
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "training" / "dataset" / "orpo-pairs.jsonl"
OUT = ROOT / "training" / "cloud" / "round20-orpo-train.jsonl"
META = ROOT / "training" / "cloud" / "round20.meta.json"

MIN_LEN = 10


def main():
    if not PAIRS.exists():
        print(f"❌ No pairs file at {PAIRS} — run scripts/build-orpo-pairs.py first")
        return 1

    rows = []
    dropped = {"identical": 0, "tiny": 0, "malformed": 0}
    seen = set()
    with open(PAIRS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                dropped["malformed"] += 1
                continue
            instruction = (rec.get("instruction") or "").strip()
            chosen = (rec.get("chosen") or "").strip()
            rejected = (rec.get("rejected") or "").strip()
            if not instruction or len(chosen) < MIN_LEN or len(rejected) < MIN_LEN:
                dropped["tiny"] += 1
                continue
            if chosen == rejected:
                dropped["identical"] += 1
                continue
            key = f"{instruction}\u0000{chosen}\u0000{rejected}"
            if key in seen:
                continue  # exact-dup guard across pair sources
            seen.add(key)
            rows.append({"instruction": instruction, "chosen": chosen, "rejected": rejected})

    if not rows:
        print("❌ No usable ORPO pairs — keep capturing (run-orpo-seed.py) then rebuild")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "round": 20,
        "train_type": "orpo",
        "pairs": len(rows),
        "source_pairs_file": str(PAIRS.relative_to(ROOT)),
        "dropped": dropped,
        "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "note": "ORPO preference tuning — chosen=tsc-clean final, rejected=first draft (same instruction). Resume: vaca-r19-adapter.",
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"✅ ORPO corpus: {len(rows)} pairs → {OUT.name} (dropped {sum(dropped.values())}: {dropped})")
    print(f"   meta: {META.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
