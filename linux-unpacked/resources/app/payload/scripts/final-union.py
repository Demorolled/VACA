#!/usr/bin/env python3
"""Union of all genuinely-new sources, deduped against each other + existing."""
import importlib.util
import json

spec = importlib.util.spec_from_file_location('g', 'scripts/build-new-bible-patterns.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

pairs, hashes = g.collect_existing()
print('existing pairs:', len(pairs))

candidates = []

# gui_trainer datasets (complete project code)
for fn in ['gui-combined.jsonl', 'gui-projects.jsonl', 'gui-components.jsonl',
           'gui-js-patterns.jsonl', 'gui-css-patterns.jsonl', 'gui-design.jsonl']:
    for r in g.load_jsonl('training/gui_trainer/datasets/' + fn):
        out = str(r.get('output') or '')
        if len(out) < 100:
            continue
        candidates.append({'instruction': str(r.get('instruction') or ''),
                           'input': str(r.get('input') or ''),
                           'output': out,
                           'source': 'gui-' + fn})

# patterns.json (TypeScript-heavy, complete code)
pats = json.load(open('knowledge/patterns.json'))
for p in pats:
    code = str(p.get('code') or '')
    if len(code) < 150:
        continue
    title = p.get('title') or 'pattern'
    lang = p.get('language') or 'typescript'
    candidates.append({
        'instruction': f'Write a {lang} module that implements the pattern "{title}". Implement {title}.',
        'input': '',
        'output': code,
        'source': 'patterns-json',
    })

seen_pairs = set()
seen_hashes = set()
kept = []
dropped = 0
for r in candidates:
    k = (r['instruction'], r['output'])
    h = g.code_hash(r['output'])
    if k in pairs or k in seen_pairs or h in hashes or h in seen_hashes:
        dropped += 1
        continue
    seen_pairs.add(k)
    seen_hashes.add(h)
    kept.append(r)

print('candidates:', len(candidates))
print('dropped:', dropped)
print('KEPT union:', len(kept))

from collections import Counter
print('by source:', dict(Counter(r['source'] for r in kept)))
# sample
print('\n=== samples ===')
for r in kept[:3]:
    print('---', r['source'], '|', r['instruction'][:90])
    print(r['output'][:200].replace('\n', ' | '))
