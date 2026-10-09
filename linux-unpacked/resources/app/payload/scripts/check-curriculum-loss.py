#!/usr/bin/env python3
"""Compare current BIBLE_LEVEL_TOPICS keys vs the backup copy to detect any
hand-written curriculum-level loss introduced by the rebuild."""
import re
import os

ROOT = '/home/final-flash1/Desktop/visual-ai-architect'
os.chdir(ROOT)

CUR = os.path.join(ROOT, 'backend', 'src', 'ai', 'libraryContext.ts')
BAK = os.path.join(ROOT, '$BACKUP_DIR', 'backend', 'src', 'ai', 'libraryContext.ts')


def topics_keys(path):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'const BIBLE_LEVEL_TOPICS.*?\{(.*?)\n\};', src, re.S)
    if not m:
        return None
    return set(re.findall(r"'([a-z0-9][a-z0-9-]+)':\s*\[", m.group(1)))


cur = topics_keys(CUR)
bak = topics_keys(BAK)
print('current topics keys:', len(cur))
print('backup topics keys:', len(bak))
print('numbered 01-..42 levels in current:', sum(1 for k in cur if re.match(r'^\d{2}-', k)))
print('numbered levels in backup:', sum(1 for k in bak if re.match(r'^\d{2}-', k)))

# keys in backup that are NOT chunk ids and NOT in current
missing = bak - cur
# load chunk ids
import importlib.util
chunk_ids = set()
for fn in sorted(os.listdir(os.path.join(ROOT, 'data', 'code-bible'))):
    if not fn.endswith('.py'):
        continue
    spec = importlib.util.spec_from_file_location('x_' + fn[:-3], os.path.join(ROOT, 'data', 'code-bible', fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    chunk_ids.update(c['id'] for c in getattr(mod, 'CHUNKS', []))
hand_missing = sorted(missing - chunk_ids)
print('hand-written keys missing from current (vs backup):', len(hand_missing))
for k in hand_missing:
    print('  ', k)
