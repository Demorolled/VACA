#!/usr/bin/env python3
"""Quick progress report for the round-8 code distillation build."""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(ROOT, 'training', 'dataset', 'round8-code.jsonl')
TARGET = 10_000_000

if not os.path.exists(path):
    print('output file not found yet')
    sys.exit(0)

rows = []
for line in open(path, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except json.JSONDecodeError:
        print('!! partial/truncated line found (resume hygiene would trim it)')

tot = os.path.getsize(path)
n = len(rows)
avg = tot / n if n else 0
proj_rows = TARGET / avg if avg else 0
regs = Counter(r.get('source', '').split(':')[1] for r in rows)

print(f'rows: {n}')
print(f'bytes: {tot/1e6:.2f} MB / {TARGET/1e6:.0f} MB target')
print(f'avg row: {avg:.0f} bytes')
print(f'projected rows needed at this avg: {proj_rows:.0f}')
print(f'registers ({len(regs)}): {dict(regs)}')
plan = sum(1 for r in rows if r.get('source', '').startswith('distill:planning'))
print(f'planning rows: {plan}')
