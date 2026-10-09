#!/usr/bin/env python3
"""
Compile the Round-28 14B training corpus.

The 14B R20 was last trained on R18-R20 data (Aug 17). Rounds 21-25 generated
~2,700 more rows the 14B has never seen. This round catches it up:

  A. round25/all.jsonl        (2,769 rows — the compiled R21-25 VACA corpus)
  B. round28-distill-27b.jsonl (~400 rows — the 27B's answers, distilled)

Deduplicates by (instruction, output) hash; A wins on collision (keep the
verified VACA data), B adds the 27B's behavior on rows it didn't already
answer. Writes round28-train.jsonl + meta.
"""
import argparse
import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "round28-train.jsonl"
META = ROOT / "training" / "cloud" / "round28.meta.json"

SOURCES = [
    ("round25-all", ROOT / "training" / "cloud" / "round25" / "all.jsonl"),
    ("distill-27b", ROOT / "training" / "cloud" / "round28-distill-27b.jsonl"),
]


def row_hash(r):
    return hashlib.sha256(
        (str(r.get("instruction", "")) + "\x00" + str(r.get("output", ""))[:200]).encode()
    ).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=0)
    args = ap.parse_args()

    seen = set()
    kept = Counter()
    total = Counter()
    with open(OUT, "w", encoding="utf-8") as f:
        for label, path in SOURCES:
            if not path.exists():
                print(f"  ⚠️  skip {label}: {path} missing")
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total[label] += 1
                out = {
                    "instruction": r.get("instruction", ""),
                    "input": r.get("input", ""),
                    "output": r.get("output", ""),
                    "source": f"r28:{label}",
                    "category": r.get("category", "?"),
                }
                h = row_hash(out)
                if h in seen:
                    continue
                seen.add(h)
                f.write(json.dumps(out) + "\n")
                kept[label] += 1
                if args.max_rows and sum(kept.values()) >= args.max_rows:
                    break
            print(f"  {label:16s} total={total[label]:5d} kept={kept[label]:5d}")

    META.write_text(json.dumps({
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "round": 28,
        "base_model": "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored",
        "purpose": ("14B catch-up round: R21-25 VACA corpus the R20 14B never saw, "
                    "plus ~400 rows distilled from the 27B AEON (behavior transfer)."),
        "total_rows": sum(kept.values()),
        "by_source": dict(kept),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\n  → {OUT.name}: {sum(kept.values())} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
