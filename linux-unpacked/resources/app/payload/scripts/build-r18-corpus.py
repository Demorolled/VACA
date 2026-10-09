#!/usr/bin/env python3
"""
Build the Round-18 corpus for the Qwen2.5-Coder-14B-Instruct-Uncensored fine-tune.

CONTINUATION round (resumes from the R17 LoRA). Mixes, in priority order:
  A. R16 anti-fence corpus (clean-only code rows — the deployed 7B's knowledge)
  B. Ladder-R1 verified rows (156 blueprint module files)
  C. round7-emotion distillation (1276 rows — the Gemma emotional register)
  D. Current verified-generations rows (source blueprint-verified:* — includes
     today's 48 new captures: unit-converter, temperature-converter, chess,
     checkers, calculator, tip-calc, password-gen, stopwatch, todo-list)
  E. teacher repair-pairs (6 rows — the teacher loop's bug→fix pairs from the
     seq 8/11/12/13 repair session; a NEW source that R17 did not have)

Deduplicates by (instruction, output) hash; keeps the FIRST occurrence from the
higher-priority source. Writes training/cloud/round18-train.jsonl + a meta file
with the per-source breakdown (same shape as round17.meta.json).

Usage:
  python3 scripts/build-r18-corpus.py                    # full ~2,100-row corpus
  python3 scripts/build-r18-corpus.py --max-rows 1500    # trimmed fallback

Trim mode (--max-rows N): keeps rows in source-priority order — R16 clean-code
first (611), then ladder-r1 (155), then verified, then repair-pairs, then
emotion rows fill the remaining budget. Code knowledge is always preserved.
"""
import argparse
import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "round18-train.jsonl"
META = ROOT / "training" / "cloud" / "round18.meta.json"

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
    ap = argparse.ArgumentParser(description="Build R18 corpus (full or trimmed)")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="Cap total rows (0 = full corpus). Trim keeps code sources first.")
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
                src = r.get("source") or ""
                if prefixes is not None and not src.startswith(prefixes):
                    continue
                total[label] += 1
                out = {
                    "instruction": r.get("instruction", ""),
                    "input": r.get("input", ""),
                    "output": r.get("output", ""),
                    "source": f"r18:{label}" + (f":{src}" if src else ""),
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
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "round": 18,
        "base_model": "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored",
        "resumes_from": "round17",
        "purpose": (
            "Continuation of R17 (14B coder base): full mixed corpus PLUS today's "
            "new verified generations (48 rows: unit-converter/temp-converter/chess/"
            "checkers/calculator/tip-calc/password-gen/stopwatch/todo) and the 6 "
            "teacher repair-pairs (bug->fix examples the scope-leak lint now guides)."
        ),
        "max_rows": max_rows or None,
        "total_rows": sum(kept.values()),
        "by_source": dict(kept),
        "per_source": dict(total),
    }
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"\n  → {OUT.name}: {sum(kept.values())} rows")
    print(f"  → meta: {META.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
