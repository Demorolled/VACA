#!/usr/bin/env python3
"""Probe gui_trainer datasets for complete instruction/output code patterns."""
import json
import os

FILES = [
    'training/gui_trainer/datasets/gui-components.jsonl',
    'training/gui_trainer/datasets/gui-js-patterns.jsonl',
    'training/gui_trainer/datasets/gui-css-patterns.jsonl',
    'training/gui_trainer/datasets/gui-design.jsonl',
]

for fn in FILES:
    if not os.path.exists(fn):
        print('MISSING', fn)
        continue
    rows = [json.loads(l) for l in open(fn, encoding='utf-8') if l.strip()]
    print('=====', fn, '| rows:', len(rows))
    if not rows:
        continue
    print('  keys:', list(rows[0].keys()))
    out_len = [len(str(r.get('output') or r.get('code') or '')) for r in rows]
    out_len.sort(reverse=True)
    print('  output len: max', out_len[0] if out_len else 0,
          '| median', out_len[len(out_len)//2] if out_len else 0)
    # sample one row with substantial output
    for r in rows:
        o = str(r.get('output') or r.get('code') or '')
        if len(o) > 300:
            print('  SAMPLE instruction:', str(r.get('instruction'))[:120])
            print('  SAMPLE output head:', o[:300].replace('\n', ' | '))
            break
    print()
