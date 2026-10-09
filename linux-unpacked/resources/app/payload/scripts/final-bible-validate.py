#!/usr/bin/env python3
"""Final consolidated validation of the +400 bible chunk expansion."""
import importlib.util
import os
import re
import sys
from collections import Counter

ROOT = '/home/final-flash1/Desktop/visual-ai-architect'
os.chdir(ROOT)
ok = True


def check(label, cond, extra=''):
    global ok
    print(('PASS' if cond else 'FAIL'), '-', label, extra)
    if not cond:
        ok = False


# 1. chunk DB: load, contract, dedupe
REQUIRED = {'id', 'name', 'category', 'lang', 'when', 'why', 'tags', 'iface', 'code', 'provides', 'depends'}
chunks = []
errs = []
for fn in sorted(os.listdir(os.path.join(ROOT, 'data', 'code-bible'))):
    if not fn.endswith('.py'):
        continue
    p = os.path.join(ROOT, 'data', 'code-bible', fn)
    spec = importlib.util.spec_from_file_location('x_' + fn[:-3], p)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        errs.append('%s: %s' % (fn, e))
        continue
    for c in getattr(mod, 'CHUNKS', []):
        chunks.append(c)
        missing = REQUIRED - set(c.keys())
        if missing:
            errs.append('%s missing %s' % (c.get('id'), missing))
        if '```' in c.get('code', ''):
            errs.append('%s fence-breaker' % c.get('id'))
ids = [c['id'] for c in chunks]
dupes = [k for k, v in Counter(ids).items() if v > 1]
check('chunk DB loads, 0 errors', not errs, '(%d errs)' % len(errs))
for e in errs[:5]:
    print('   ', e)
check('no duplicate ids', not dupes, str(dupes[:3]) if dupes else '')
check('total chunks = 904', len(chunks) == 904, '(%d)' % len(chunks))

# 2. topics map coverage
src = open(os.path.join(ROOT, 'backend', 'src', 'ai', 'libraryContext.ts'), encoding='utf-8').read()
m = re.search(r'const BIBLE_LEVEL_TOPICS.*?\{(.*?)\n\};', src, re.S)
keys = set(re.findall(r"'([a-z0-9][a-z0-9-]+)':\s*\[", m.group(1)))
check('all chunk ids in BIBLE_LEVEL_TOPICS', set(ids).issubset(keys),
      '(%d topics keys, %d chunks)' % (len(keys), len(ids)))
# 2b. curriculum-level coverage: all 56 numbered curriculum keys must survive
# (protects against a rebuild silently dropping hand-written levels)
numeric = set(k for k in keys if re.match(r'^\d{2}-', k))
check('all numbered curriculum levels present', len(numeric) >= 56, '(%d numbered)' % len(numeric))

# 3. node + lang maps present and curated ids present
for name in ['NODE_TYPE_TO_BIBLE_LEVELS', 'LANGUAGE_TO_BIBLE_LEVELS', 'NODE_TYPE_TO_FILES', 'LANGUAGE_TO_FILES']:
    check('map %s present' % name, ('const ' + name + ':') in src)

# 4. scaffold + MASTER-INDEX
mi = open(os.path.join(ROOT, 'bible-reference', 'MASTER-INDEX.txt'), encoding='utf-8').read()
check('MASTER-INDEX header has 904 chunks', '904 atomic code chunks' in mi)
check('MASTER-INDEX header has 42 levels', '42 levels' in mi)

# 5. datasheets.yaml valid + version 3.0
import yaml
y = yaml.safe_load(open(os.path.join(ROOT, 'training', 'datasheets.yaml')))
ds = [d for d in y['datasheets'] if d['id'] == 'code-bible-expansion'][0]
check('datasheets.yaml valid + v3.0', str(ds['version']) == '3.0' and ds['examples'] == 700)

print()
print('ALL PASS' if ok else 'FAILURES PRESENT')
sys.exit(0 if ok else 1)
