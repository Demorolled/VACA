#!/usr/bin/env python3
"""Final source math for the new bible pattern set."""
import importlib.util
import json
import re

spec = importlib.util.spec_from_file_location('g', 'scripts/build-new-bible-patterns.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

pairs, hashes = g.collect_existing()
print('existing pairs:', len(pairs), '| existing code hashes:', len(hashes))


def dedupe_rows(rows):
    seen_pairs = set()
    kept = 0
    for r in rows:
        k = (r.get('instruction', ''), r.get('output', ''))
        h = g.code_hash(r.get('output', ''))
        if not r.get('output') or len(str(r.get('output'))) < 100:
            continue
        if k in pairs or k in seen_pairs or h in hashes:
            continue
        seen_pairs.add(k)
        kept += 1
    return kept


# gui-combined
gc = g.load_jsonl('training/gui_trainer/datasets/gui-combined.jsonl')
print('\ngui-combined rows:', len(gc), '| survive dedupe:', dedupe_rows(gc))

# gui-projects
gp = g.load_jsonl('training/gui_trainer/datasets/gui-projects.jsonl')
print('gui-projects rows:', len(gp), '| survive dedupe:', dedupe_rows(gp))

# patterns.json (code >= 150)
pats = json.load(open('knowledge/patterns.json'))
pat_rows = [{'instruction': f'Write a TypeScript module that implements the pattern "{p.get("title")}". Implement {p.get("title")}.',
             'input': '', 'output': str(p.get('code') or '')}
            for p in pats if len(str(p.get('code') or '')) >= 150]
print('patterns.json rows (>=150):', len(pat_rows), '| survive dedupe:', dedupe_rows(pat_rows))

# strict md impls: real body heuristic (has => { or function { with body > 400)
chunks = g.new_chunks()
strict = [c for c in chunks if len(c['code']) >= 400 and re.search(r'[=)]\s*=>\s*\{', c['code'])]
print('\nmd chunks (strict real impl, >=400 chars + arrow body):', len(strict))
for c in strict[:3]:
    print('  ', c['path'], '|', c['code'][:120].replace('\n', ' '))
