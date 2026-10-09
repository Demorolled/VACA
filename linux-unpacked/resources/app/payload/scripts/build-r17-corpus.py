#!/usr/bin/env python3
"""
Build the Round-17 corpus for the Qwen2.5-Coder-14B-Instruct-Uncensored fine-tune.

Mixes, in priority order:
  A. R16 anti-fence corpus (clean-only code rows — the deployed 7B's knowledge)
  B. Ladder-R1 verified rows (156 blueprint module files — this session's data)
  C. round7-emotion distillation (1276 rows — the Gemma emotional register that
     R16's code-focused corpus DROPPED; restored so the 14B keeps VACA's soul)
  D. Current verified-generations rows (source blueprint-verified:*)

Deduplicates by (instruction, output) hash; keeps the FIRST occurrence from the
higher-priority source. Writes training/cloud/round17-train.jsonl + a meta file
with the per-source breakdown (same shape as round16-antifence.meta.json).

Usage:
  python3 scripts/build-r17-corpus.py                # full 2,063-row corpus
  python3 scripts/build-r17-corpus.py --max-rows 1500  # trimmed fallback

Trim mode (--max-rows N): keeps rows in source-priority order — R16 clean-code
first (611), then ladder-r1 (155), then verified (22), then emotion rows fill
the remaining budget. This preserves ALL code knowledge and only trims the
lower-density emotion rows, so the fallback still fits the 12h T4 session cap.
"""
import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "round17-train.jsonl"
META = ROOT / "training" / "cloud" / "round17.meta.json"

SOURCES = [
    # (label, path, filter_source_prefix)
    ("round16-antifence-all", ROOT / "training" / "cloud" / "round16-antifence-all.jsonl", None),
    ("ladder-r1", ROOT / "training" / "cloud" / "ladder-r1-train.jsonl", None),
    ("round7-emotion", ROOT / "dataset" / "round7-emotion.jsonl", None),
    ("verified-generations", ROOT / "training" / "dataset" / "verified-generations.jsonl", "blueprint-verified"),
]


def row_hash(r):
    return hashlib.sha256(
        (str(r.get("instruction", "")) + "\x00" + str(r.get("output", ""))).encode()
    ).hexdigest()


# Source priority for TRIM mode (code knowledge first, emotion fills remainder)
TRIM_PRIORITY = [
    "round16-antifence-all",
    "ladder-r1",
    "verified-generations",
    "round7-emotion",
]


def main():
    ap = argparse.ArgumentParser(description="Build R17 corpus (full or trimmed)")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="Cap total rows (0 = full corpus). Trim keeps code sources first.")
    args = ap.parse_args()
    max_rows = args.max_rows

    src_map = {label: (path, prefix) for label, path, prefix in SOURCES}
    order = TRIM_PRIORITY if max_rows else [s[0] for s in SOURCES]

    seen = set()
    kept = Counter()
    total = Counter()
    with open(OUT, "w", encoding="utf-8") as f:
        for label in order:
            path, prefix = src_map[label]
            if not path.exists():
                print(f"  ⚠️  skip {label}: {path} missing")
                continue
            n = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                if max_rows and len(seen) >= max_rows:
                    break
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prefix and not (r.get("source") or "").startswith(prefix):
                    continue
                total[label] += 1
                out = {
                    "instruction": r.get("instruction", ""),
                    "input": r.get("input", ""),
                    "output": r.get("output", ""),
                    "source": f"r17:{label}" + (f":{r.get('source')}" if r.get("source") else ""),
                }
                h = row_hash(out)
                if h in seen:
                    continue
                seen.add(h)
                f.write(json.dumps(out) + "\n")
                kept[label] += 1
                n += 1
            print(f"  {label:24s} total={total[label]:5d} kept={kept[label]:5d}")
            if max_rows and len(seen) >= max_rows:
                break

    meta = {
        "generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
        "round": 17,
        "base_model": "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored",
        "purpose": (
            "First 14B round: coder-specialized uncensored base + R16 clean-code "
            "corpus + ladder-r1 verified modules + restored round7-emotion register."
        ),
        "max_rows": max_rows or None,
        "total_rows": sum(kept.values()),
        "by_source": dict(kept),
        "per_source": {
            label: {"total": total[label], "kept": kept[label]}
            for label in SOURCES if total[label] > 0
        },
    }
    META.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"\n  ✅ Wrote {OUT} ({sum(kept.values())} rows)")
    print(f"     Meta: {META}")


if __name__ == "__main__":
    main()
