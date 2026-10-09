#!/usr/bin/env python3
"""
Build the Round-5 full-knowledge blueprint fine-tune dataset (NO leakage).
=========================================================================
Round 3 trained on the FULL blueprint-pairs.jsonl (1,230 rows) INCLUDING the
61 test + 61 val instructions, so its 59% fidelity score was partly
memorization. Round 4 trained only on the 25 failures (401 rows) and drifted
the app_type vocabulary (59.0% -> 45.9%: 11 fixed, 19 regressed).

Round-5 fixes both by training on the CLEAN knowledge split:

  * blueprint-pairs-train.jsonl (1,108 rows / 1,108 distinct app types) —
    the held-out 122 rows (val + test) are NEVER in this file, so the model
    must generalize to sibling phrasings instead of memorizing them.
  * round4-failures.jsonl reinforcement (OPT-IN, ROUND5_INCLUDE_R4=1) —
    the 25-failure canonical pairs. Default OFF: 33 of the 61 test
    instructions live in that file, so including it re-creates the round-3
    leakage problem round-5 exists to fix. Enable only if you accept that
    the eval partially measures recall again.
  * VACA_MIX=N retention mix (default 300) — N rows sampled (seed 42, the
    same provenance as round 4) from round3-mixed.jsonl. Retention adds the
    300 code-generation/prose rows verbatim (never re-parsed) so the focused
    round does not forget how to write code. Blueprint rows from the mix are
    deduped against train (already present).

Eval is unchanged and stays truly held out:
  * blueprint-pairs-val.jsonl (61)  — used by the engine's validation split
  * blueprint-pairs-test.jsonl (61) — used by validate-blueprint-fidelity.py

Output (Alpaca JSONL — the exact format GUITrainer.load_gui_dataset() reads):
    {"instruction": "<user request>", "input": "", "output": "<blueprint JSON>"}

Usage:
  python3 scripts/build-round5-blueprints-dataset.py
  ROUND5_INCLUDE_R4=0 VACA_MIX=0 python3 scripts/build-round5-blueprints-dataset.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN_SPLIT = os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-train.jsonl')
R4 = os.path.join(BASE, 'training', 'dataset', 'round4-failures.jsonl')
ROUND3 = os.path.join(BASE, 'training', 'dataset', 'round3-mixed.jsonl')
OUT = os.path.join(BASE, 'training', 'dataset', 'round5-blueprints.jsonl')
STATS = os.path.join(BASE, 'training', 'dataset', 'round5-blueprints-stats.json')


def load_rows(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return rows


def main():
    include_r4 = os.environ.get('ROUND5_INCLUDE_R4', '0') != '0'
    mix_n = int(os.environ.get('VACA_MIX', '300'))

    # Eval-exclusion: the historical split is NOT a clean partition — 13 test +
    # 11 val rows are byte-identical to rows in the train split (plus the r4
    # reinforcement duplicates more). Round-5 must never train on an eval row,
    # so exclude those exact (instruction, output) pairs from train.
    eval_rows = load_rows(os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-val.jsonl')) \
        + load_rows(os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-test.jsonl'))
    eval_keys = {(r.get('instruction', ''), r.get('output', '')) for r in eval_rows}

    train = load_rows(TRAIN_SPLIT)
    seen = set()
    examples = []
    stripped = 0
    for r in train:
        key = (r.get('instruction', ''), r.get('output', ''))
        if key in seen:
            continue
        if key in eval_keys:
            stripped += 1
            continue
        seen.add(key)
        examples.append({'instruction': r.get('instruction', ''),
                         'input': r.get('input', ''),
                         'output': r.get('output', '')})

    src_counts = {'blueprint-pairs-train.jsonl': len(examples)}
    print(f'[r5] stripped {stripped} eval-duplicate rows from train split')

    if include_r4:
        r4 = load_rows(R4)
        added = 0
        for r in r4:
            key = (r.get('instruction', ''), r.get('output', ''))
            if key in seen:
                continue
            seen.add(key)
            examples.append({'instruction': r.get('instruction', ''),
                             'input': r.get('input', ''),
                             'output': r.get('output', '')})
            added += 1
        src_counts['round4-failures.jsonl'] = added

    if mix_n > 0:
        mixed = load_rows(ROUND3)
        import random
        random.seed(42)
        sample = random.sample(mixed, min(mix_n, len(mixed)))
        added = 0
        for r in sample:
            key = (r.get('instruction', ''), r.get('output', ''))
            if key in eval_keys:  # retention must not re-leak eval rows
                continue
            if key in seen:
                continue
            seen.add(key)
            examples.append({'instruction': r.get('instruction', ''),
                             'input': r.get('input', ''),
                             'output': r.get('output', '')})
            added += 1
        src_counts['round3-mixed.jsonl (retention)'] = added

    with open(OUT, 'w', encoding='utf-8') as f:
        for rec in examples:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    types = set()
    for r in examples:
        try:
            o = json.loads(r.get('output', '{}'))
            if isinstance(o, dict) and o.get('app_type'):
                types.add(o['app_type'])
        except json.JSONDecodeError:
            pass

    # Eval-ceiling: the test split is row-level on a 1-row-per-type dataset, so
    # ~half the test app_types have NO row in the train split. Those can never
    # pass the exact/fidelity gates (unseen key) — only the known gate (emit a
    # valid library key). This is the honest ceiling to compare round-5 against.
    test_rows = load_rows(os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-test.jsonl'))
    train_types = set(types)
    test_types = set()
    for r in test_rows:
        try:
            o = json.loads(r.get('output', '{}'))
            if isinstance(o, dict) and o.get('app_type'):
                test_types.add(o['app_type'])
        except json.JSONDecodeError:
            pass
    test_types_in_train = len(test_types & train_types)

    stats = {
        'generated': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'total_examples': len(examples),
        'distinct_app_types': len(types),
        'sources': src_counts,
        'eval_held_out': {
            'blueprint-pairs-val.jsonl': len(load_rows(os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-val.jsonl'))),
            'blueprint-pairs-test.jsonl': len(test_rows),
        },
        'eval_ceiling': {
            'test_app_types_total': len(test_types),
            'test_app_types_present_in_train': test_types_in_train,
            'exact_fidelity_ceiling_pct': round(100 * test_types_in_train / max(len(test_types), 1), 1),
            'note': 'row-level split: app types with no train row cannot pass exact/fidelity gates; known gate is their best case.',
        },
        'split_fixes': {'eval_duplicate_rows_stripped_from_train': stripped},
        'note': 'train split (1108) never contains the val/test instructions. ROUND5_INCLUDE_R4 defaults OFF to keep the eval honest.',
    }
    with open(STATS, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)

    print(f'[r5] examples written: {len(examples)} | distinct app types: {len(types)}')
    print(f'[r5] sources: {src_counts}')
    print(f'[r5] -> {OUT} (+ stats at {STATS})')


if __name__ == '__main__':
    main()
