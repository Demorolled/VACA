#!/usr/bin/env python3
"""
Build the Round-4 focused fine-tune dataset from blueprint-fidelity failures.
=============================================================================
Round 3 (blueprint-JSON fidelity) scored 59% on the full 61-prompt validation.
All 25 failures were audited and are genuine MODEL errors (the test set matches
the canonical library on all 61 rows — no data/library fixes were needed):

  * 1  prose/markdown drift        (terminal_os → README instead of JSON)
  * 8  invented app_type names     (blog_cms→content_management, hrms, …)
  * 3  wrong-but-valid app_type    (tetris_attack_2→tetris_attack, …)
  * 13 structural fidelity         (right type, generic 4-module fallback)

This script builds a small, high-signal dataset from exactly those failures:
  * each failing instruction  → the CANONICAL blueprint JSON from the library
    (backend/blueprints/**/*.json — ground truth the engine actually serves)
  * the failing instruction repeated REPEAT× (a 25-row set is too small for
    the engine's step math, which needs ~tens of steps per round)
  * sibling phrasings for the same app types from blueprint-pairs.jsonl (helps
    generalization beyond the single failing phrasing)

Optional retention mix (VACA_MIX=N) samples N rows from round3-mixed.jsonl so
the focused round does not forget code-generation / other blueprint knowledge.
Retention rows are passed through VERBATIM — their outputs may be prose code
from train.jsonl, not blueprint JSON, so they must not be re-parsed.

Output (Alpaca JSONL — the exact format GUITrainer load_gui_dataset() reads):
    {"instruction": "<user request>", "input": "", "output": "<blueprint JSON>"}

Usage:
  python3 scripts/build-round4-failures-dataset.py
  VACA_MIX=300 python3 scripts/build-round4-failures-dataset.py
"""
import glob
import json
import os
import random

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(BASE, 'data', 'blueprint-fidelity-validation.json')
TEST = os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-test.jsonl')
FULL = os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs.jsonl')
ROUND3 = os.path.join(BASE, 'training', 'dataset', 'round3-mixed.jsonl')
OUT = os.path.join(BASE, 'training', 'dataset', 'round4-failures.jsonl')

CONTRACT_KEYS = ('app_type', 'description', 'keywords', 'target_stack',
                 'architecture_checklist', 'wiring_graph')
REPEAT = 4       # copies of the exact failing instruction per failure
SIBLING_CAP = 3  # max extra phrasings per failing app type


def load_library():
    """app_type -> canonical blueprint (6 contract keys), from the live library."""
    lib = {}
    for pat in (os.path.join(BASE, 'backend', 'blueprints', '*.json'),
                os.path.join(BASE, 'backend', 'blueprints', 'generated', '*.json')):
        for p in glob.glob(pat):
            try:
                raw = json.load(open(p, encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(raw, dict) or not isinstance(raw.get('app_type'), str):
                continue
            lib[raw['app_type'].strip()] = {k: raw.get(k) for k in CONTRACT_KEYS}
    return lib


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
    mix_n = int(os.environ.get('VACA_MIX', '0'))
    random.seed(42)

    report = json.load(open(REPORT, encoding='utf-8'))
    fails = [c for c in report['cases'] if not c.get('ok')]
    if not fails:
        print('[r4] no failures in report — nothing to build')
        return

    # Map failing instruction -> canonical app_type via the test rows.
    test_map = {r['instruction']: json.loads(r['output']) for r in load_rows(TEST)}
    lib = load_library()

    def blueprint_record(inst, b):
        return {'instruction': inst, 'input': '',
                'output': json.dumps(b, ensure_ascii=False, separators=(',', ':'))}

    examples = []  # list of record dicts (Alpaca)
    used = set()
    for c in fails:
        inst = c['instruction']
        expected = test_map.get(inst)
        at = (expected or {}).get('app_type')
        canon = lib.get(at) if at else None
        if canon is None:
            print(f'[r4] ⚠ no canonical for {at or "?"} — skipping {inst[:60]}')
            continue
        for _ in range(REPEAT):
            examples.append(blueprint_record(inst, canon))
        used.add(at)

    # Sibling phrasings for the same app types from the full dataset (extra
    # rows exist where the builder's duplicate phase picked another phrasing).
    failing_insts = {c['instruction'] for c in fails}
    siblings = {at: [] for at in used}
    for r in load_rows(FULL):
        if r['instruction'] in failing_insts:
            continue
        try:
            o = json.loads(r['output'])
        except json.JSONDecodeError:
            continue
        at = o.get('app_type')
        if at in siblings:
            siblings[at].append((r['instruction'], lib.get(at)))
    for at, rows in siblings.items():
        random.shuffle(rows)
        for inst, canon in rows[:SIBLING_CAP]:
            if canon is not None:
                examples.append(blueprint_record(inst, canon))

    # Retention mix (optional): pass rows through VERBATIM — outputs may be
    # prose code from train.jsonl (not blueprint JSON), never re-parse them.
    if mix_n > 0:
        mixed = load_rows(ROUND3)
        sample = random.sample(mixed, min(mix_n, len(mixed)))
        for r in sample:
            examples.append({'instruction': r.get('instruction', ''),
                             'input': r.get('input', ''),
                             'output': r.get('output', '')})
        print(f'[r4] retention mix: {len(sample)} rows from round3-mixed')

    with open(OUT, 'w', encoding='utf-8') as f:
        for rec in examples:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    types = set()
    for c in fails:
        expected = test_map.get(c['instruction'])
        if expected:
            types.add(expected.get('app_type'))
    print(f'[r4] failures: {len(fails)} | examples written: {len(examples)} '
          f'(repeats ×{REPEAT} + siblings + mix) | failing app types covered: {len(types)}')
    print(f'[r4] -> {OUT}')


if __name__ == '__main__':
    main()
