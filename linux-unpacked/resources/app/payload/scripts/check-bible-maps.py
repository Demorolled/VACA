#!/usr/bin/env python3
"""Verify BIBLE_LEVEL_TOPICS / node / lang map coverage in libraryContext.ts."""
import importlib.util
import os
import re
from collections import Counter

ROOT = '/home/final-flash1/Desktop/visual-ai-architect'
os.chdir(ROOT)
src = open(os.path.join(ROOT, 'backend', 'src', 'ai', 'libraryContext.ts'), encoding='utf-8').read()

# chunk ids
ids = []
for fn in sorted(os.listdir(os.path.join(ROOT, 'data', 'code-bible'))):
    if not fn.endswith('.py'):
        continue
    spec = importlib.util.spec_from_file_location('x_' + fn[:-3], os.path.join(ROOT, 'data', 'code-bible', fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ids.extend(c['id'] for c in mod.CHUNKS)
chunk_ids = set(ids)

# topics
m = re.search(r'const BIBLE_LEVEL_TOPICS.*?\{(.*?)\n\};', src, re.S)
keys = set(re.findall(r"'([a-z0-9][a-z0-9-]+)':\s*\[", m.group(1)))
print('BIBLE_LEVEL_TOPICS keys:', len(keys))
print('all chunks in topics:', chunk_ids.issubset(keys))
print('chunks NOT in topics:', sorted(chunk_ids - keys) or 'none')

# node map
nm = re.search(r'const NODE_TYPE_TO_BIBLE_LEVELS.*?\{(.*?)\n\};', src, re.S)
node = dict(re.findall(r'(\w+):\s*\[([^\]]*)\]', nm.group(1)))
for nt, body in node.items():
    n = [x.strip("' ") for x in body.split(',') if x.strip()]
    prefs = Counter(x.split('-')[0] for x in n)
    newish = [x for x in n if x.split('-')[0] in
              {'alg','arch','str','col','fsys','time','msg','http','acc','i18n','fin','edu','gen','viz','cli','embed'}]
    print('  NODE %-9s total=%3d newcats=%d sample=%s' % (nt, len(n), len(newish), newish[:3]))

# lang map
lm = re.search(r'const LANGUAGE_TO_BIBLE_LEVELS.*?\{(.*?)\n\};', src, re.S)
lang = dict(re.findall(r'(\w+):\s*\[([^\]]*)\]', lm.group(1)))
for lg, body in lang.items():
    n = [x.strip("' ") for x in body.split(',') if x.strip()]
    newish = [x for x in n if x.split('-')[0] in
              {'alg','arch','str','col','fsys','time','msg','http','acc','i18n','fin','edu','gen','viz','cli','embed'}]
    print('  LANG %-10s total=%3d newcats=%d sample=%s' % (lg, len(n), len(newish), newish[:3]))
