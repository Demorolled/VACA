#!/usr/bin/env python3
"""
Combine ALL recent GUI-design training data into a single deduped dataset.
=========================================================================
Merges the GUI trainer's datasets (gui_trainer/datasets/gui-*.jsonl — the
gui-projects rows, synthetic component/css/design/js patterns, and the
previously combined file) with the freshly built DESIGN-TOKENS rows
(training/dataset/gui-design.jsonl). Rows are deduped by content hash
(instruction|input|output) keeping the FIRST occurrence.

Outputs (schema-compatible with train_round1.py / the local engine):
    training/cloud/gui-combined-all.jsonl   full merged corpus
    training/cloud/gui-train.jsonl          ~90% split
    training/cloud/gui-val.jsonl            ~10% split
    training/cloud/gui-combined-all.meta.json  row counts per source

Usage:
  python3 scripts/combine-gui-datasets.py                # write all outputs
  python3 scripts/combine-gui-datasets.py --dry-run      # stats only
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = [
    ROOT / 'training/gui_trainer/datasets/gui-combined.jsonl',
    ROOT / 'training/gui_trainer/datasets/gui-components.jsonl',
    ROOT / 'training/gui_trainer/datasets/gui-css-patterns.jsonl',
    ROOT / 'training/gui_trainer/datasets/gui-design.jsonl',
    ROOT / 'training/gui_trainer/datasets/gui-js-patterns.jsonl',
    ROOT / 'training/gui_trainer/datasets/gui-projects.jsonl',
    ROOT / 'training/dataset/gui-design.jsonl',
]

OUT_FULL = ROOT / 'training/cloud/gui-combined-all.jsonl'
OUT_TRAIN = ROOT / 'training/cloud/gui-train.jsonl'
OUT_VAL = ROOT / 'training/cloud/gui-val.jsonl'
OUT_META = ROOT / 'training/cloud/gui-combined-all.meta.json'

SEED = 42
VAL_FRACTION = 0.10


def row_key(rec) -> str:
    return hashlib.md5(
        f"{rec.get('instruction', '')}|{rec.get('input', '')}|{rec.get('output', '')}"
        .encode('utf-8')
    ).hexdigest()


def main():
    ap = argparse.ArgumentParser(description='Merge + dedupe the GUI training datasets')
    ap.add_argument('--dry-run', action='store_true', help='stats only, no write')
    args = ap.parse_args()

    seen = {}
    per_source = Counter()
    for path in SOURCE_FILES:
        if not path.exists():
            print(f'  ⚠️  missing: {path.name}')
            continue
        n = 0
        for line in path.open(encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = row_key(rec)
            if k not in seen:
                seen[k] = rec
                per_source[path.name] += 1
            n += 1
        print(f'  {path.name:32s} {n:4d} rows → {per_source[path.name]:4d} kept')

    rows = list(seen.values())
    print(f'\n  Total unique rows: {len(rows)}')

    if args.dry_run:
        print('  --dry-run: nothing written')
        sys.exit(0)

    OUT_FULL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FULL.open('w', encoding='utf-8') as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    # Deterministic 90/10 train/val split
    rng = __import__('random').Random(SEED)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    val_count = max(1, int(len(rows) * VAL_FRACTION))
    val_idx = set(idx[:val_count])

    with OUT_TRAIN.open('w', encoding='utf-8') as f:
        for i, rec in enumerate(rows):
            if i not in val_idx:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    with OUT_VAL.open('w', encoding='utf-8') as f:
        for i, rec in enumerate(rows):
            if i in val_idx:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    meta = {
        'total_rows': len(rows),
        'train_rows': len(rows) - len(val_idx),
        'val_rows': len(val_idx),
        'val_fraction': VAL_FRACTION,
        'seed': SEED,
        'per_source': dict(per_source),
    }
    OUT_META.write_text(json.dumps(meta, indent=2) + '\n')

    print(f'\n  ✅ Wrote:')
    print(f'     {OUT_FULL.name} ({len(rows)} rows)')
    print(f'     {OUT_TRAIN.name} ({meta["train_rows"]} rows)')
    print(f'     {OUT_VAL.name} ({meta["val_rows"]} rows)')
    print(f'     {OUT_META.name}')


if __name__ == '__main__':
    main()
