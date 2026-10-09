#!/usr/bin/env python3
"""Probe larger dataset sources for complete code rows."""
import json
import os

FILES = [
    'training/gui_trainer/datasets/gui-combined.jsonl',
    'training/gui_trainer/datasets/gui-projects.jsonl',
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
    outs = [str(r.get('output') or r.get('code') or '') for r in rows]
    outs.sort(key=len, reverse=True)
    print('  output len: max', len(outs[0]) if outs else 0,
          '| median', len(outs[len(outs)//2]) if outs else 0,
          '| over 200:', sum(1 for o in outs if len(o) > 200))
    for r in rows[:2]:
        print('  INSTR:', str(r.get('instruction'))[:110])
    print()

# patterns.json: verify code quality
p = json.load(open('knowledge/patterns.json'))
print('===== patterns.json rows:', len(p))
real = [x for x in p if len(str(x.get('code') or '')) > 200]
print('  with code > 200 chars:', len(real))
for x in real[:3]:
    print('  TITLE:', x.get('title'), '| lang:', x.get('language'))
    print('  CODE:', str(x.get('code'))[:260].replace('\n', ' | '))
    print()
