#!/usr/bin/env python3
"""
Wire the new atomic code chunks into backend/src/ai/libraryContext.ts.
==========================================================================
The loader (loadBibleFiles) only reads bible-reference/<dir> where <dir> is a
key of BIBLE_LEVEL_TOPICS — any chunk slug missing from that map is silently
invisible to the LLM. This script:

  1. Loads all category files from data/code-bible/ whose category is listed
     in NEW_CATEGORIES (28 categories: the batch-2 set ml/llm/devops/db/obs/
     sec/brw/mob/test/gfx/mth/rtc plus the batch-3 set alg/arch/str/col/fsys/
     time/msg/http/acc/i18n/fin/edu/gen/viz/cli/embed).
  2. Generates 'id': [tags] entries (tags double as topics) and inserts them
     into BIBLE_LEVEL_TOPICS, sorted alphabetically before the closing '};'.
     The block close is located by declaration (first '};' line after the
     const), NOT by a hardcoded last key — the old anchor drifted across runs.
  3. Enriches NODE_TYPE_TO_BIBLE_LEVELS via a category -> node-type map so the
     new chunks surface in per-node codegen context (curated subsets).
  4. Enriches LANGUAGE_TO_BIBLE_LEVELS with a language -> category map.

Idempotent: existing 'key': entries are never duplicated.
Usage:  python3 scripts/wire-bible-chunks-into-context.py [--dry-run]
"""
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNK_DB_DIR = os.path.join(ROOT, 'data', 'code-bible')
TS = os.path.join(ROOT, 'backend', 'src', 'ai', 'libraryContext.ts')

NEW_CATEGORIES = (
    # batch 2 (300-chunk expansion)
    'ml', 'llm', 'devops', 'db', 'obs', 'sec', 'brw', 'mob', 'test', 'gfx', 'mth', 'rtc',
    # batch 3 (400-chunk expansion)
    'alg', 'arch', 'str', 'col', 'fsys', 'time', 'msg', 'http', 'acc', 'i18n',
    'fin', 'edu', 'gen', 'viz', 'cli', 'embed',
)

# Context-bloat guardrails: getLibraryContextForNodeType injects every mapped
# bible level with no cap. Keep the always-injected maps curated so a codegen
# call stays well under ~15K chars, not ~90K.
MAX_NODE_PER_CATEGORY = 5   # ids per category per node type
MAX_LANG_PER_CATEGORY = 3   # ids per category per language

# category -> node types surfaced in per-node codegen context
CATEGORY_TO_NODE_TYPES = {
    'ml':     ['logic', 'master'],
    'llm':    ['logic', 'api', 'master'],
    'devops': ['master', 'api'],
    'db':     ['database', 'api'],
    'obs':    ['master', 'api', 'database'],
    'sec':    ['api', 'database', 'ui'],
    'brw':    ['ui', 'output', 'input'],
    'mob':    ['ui', 'output'],
    'test':   ['logic', 'master'],
    'gfx':    ['output', 'ui'],
    'mth':    ['logic'],
    'rtc':    ['api', 'output', 'master'],
    # batch 3
    'alg':    ['logic', 'master'],
    'arch':   ['master', 'api'],
    'str':    ['ui', 'output', 'logic'],
    'col':    ['logic'],
    'fsys':   ['api', 'master'],
    'time':   ['logic', 'ui'],
    'msg':    ['api', 'master'],
    'http':   ['api'],
    'acc':    ['ui', 'input', 'output'],
    'i18n':   ['ui', 'output'],
    'fin':    ['logic', 'database', 'ui'],
    'edu':    ['logic', 'ui'],
    'gen':    ['master', 'api'],
    'viz':    ['output', 'ui'],
    'cli':    ['api', 'master'],
    'embed':  ['logic', 'input'],
}

# category -> languages surfaced in per-language context
CATEGORY_TO_LANGS = {
    'ml':     ['python', 'typescript'],
    'llm':    ['python', 'typescript'],
    'devops': ['python', 'go', 'typescript'],
    'db':     ['typescript', 'python', 'go'],
    'obs':    ['python', 'go', 'typescript'],
    'sec':    ['typescript', 'python', 'rust'],
    'brw':    ['typescript', 'javascript'],
    'mob':    ['typescript', 'kotlin', 'swift'],
    'test':   ['typescript', 'python'],
    'gfx':    ['typescript', 'cpp'],
    'mth':    ['typescript', 'python'],
    'rtc':    ['typescript', 'go'],
    # batch 3 (all chunks are TypeScript — surface in TS + related langs)
    'alg':    ['typescript', 'python', 'cpp'],
    'arch':   ['typescript', 'go', 'java'],
    'str':    ['typescript', 'python', 'javascript'],
    'col':    ['typescript', 'python', 'java'],
    'fsys':   ['typescript', 'python', 'go'],
    'time':   ['typescript', 'python', 'go'],
    'msg':    ['typescript', 'go', 'python'],
    'http':   ['typescript', 'python', 'go'],
    'acc':    ['typescript', 'javascript'],
    'i18n':   ['typescript', 'javascript', 'python'],
    'fin':    ['typescript', 'python'],
    'edu':    ['typescript', 'javascript'],
    'gen':    ['typescript', 'javascript'],
    'viz':    ['typescript', 'javascript', 'python'],
    'cli':    ['typescript', 'python', 'go'],
    'embed':  ['typescript', 'c', 'cpp'],
}


def load_new_chunks():
    chunks = []
    for fn in sorted(os.listdir(CHUNK_DB_DIR)):
        if not fn.endswith('.py'):
            continue
        spec = importlib.util.spec_from_file_location(f'wire_{fn[:-3]}', os.path.join(CHUNK_DB_DIR, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for c in getattr(mod, 'CHUNKS', []):
            if c.get('category') in NEW_CATEGORIES:
                chunks.append(c)
    return chunks


def main():
    dry = '--dry-run' in sys.argv
    chunks = load_new_chunks()
    if not chunks:
        raise SystemExit('No new-category chunks found — aborting')
    src = open(TS, encoding='utf-8').read()

    # ── 1. BIBLE_LEVEL_TOPICS entries ─────────────────────────────────────
    # Existing keys (so we never duplicate).
    existing = set(re.findall(r"'([a-z0-9][a-z0-9-]+)':\s*\[", src))
    entries = []
    for c in sorted(chunks, key=lambda c: c['id']):
        if c['id'] in existing:
            continue
        tags = ', '.join(f"'{t}'" for t in c.get('tags', [])[:7])
        entries.append(f"  '{c['id']}': [{tags}],")
    if not entries:
        print('BIBLE_LEVEL_TOPICS: nothing new to insert (all ids already present)')
    else:
        # Insert alphabetically before the closing '};' of BIBLE_LEVEL_TOPICS.
        # Locate the block by declaration (NOT a hardcoded last key — later
        # wire runs move the final key, so the anchor drifts).
        topics_decl = src.index('const BIBLE_LEVEL_TOPICS')
        # find the first '};' line after the declaration
        seg = src[topics_decl:]
        close_rel = seg.index('\n};')  # offset of the '};' line start
        close_abs = topics_decl + close_rel  # point at the newline BEFORE '};'
        block = '\n'.join(entries) + '\n'
        if not dry:
            src = src[:close_abs] + '\n' + block + src[close_abs:]
        print(f'BIBLE_LEVEL_TOPICS: inserting {len(entries)} new chunk entries')

    # ── 2. NODE_TYPE_TO_BIBLE_LEVELS enrichment (curated subsets) ────────
    # getLibraryContextForNodeType injects EVERY mapped level with no cap; adding
    # all 300 chunks tripled the union to ~334 levels (~24K tokens) per codegen
    # call. Fix: add at most MAX_NODE_PER_CATEGORY curated ids per category per
    # node type (deterministic first-N by id), keeping maps ~30-60 entries.
    NEW_PREFIXES = tuple(f'{c}-' for c in NEW_CATEGORIES)

    def strip_new_ids(line: str) -> str:
        """Remove previously-added new-category ids so re-runs are self-healing."""
        m = re.match(r'^(\s*\w+:\s*\[)(.*?)(\]\s*,?\s*)$', line)
        if not m:
            return line
        head, body, tail = m.group(1), m.group(2), m.group(3)
        items = [x.strip() for x in body.split(',') if x.strip()]
        kept = [x for x in items if not x.strip("' \"").startswith(NEW_PREFIXES)]
        return head + ', '.join(kept) + tail if kept else head + tail

    def append_curated(line: str, ids: list) -> str:
        m = re.match(r'^(\s*\w+:\s*\[)(.*?)(\]\s*,?\s*)$', line)
        head, body, tail = m.group(1), m.group(2), m.group(3)
        items = [x.strip() for x in body.split(',') if x.strip()]
        add = ', '.join(f"'{i}'" for i in ids)
        if items:
            return head + ', '.join(items) + ', ' + add + tail
        return head + add + tail

    src_lines = src.split('\n')
    # Find the decl line indices to scope edits strictly to the two blocks
    # (NODE_TYPE_TO_FILES / LANGUAGE_TO_FILES also contain 'key: [...]' lines).
    node_decl = next(i for i, ln in enumerate(src_lines) if 'const NODE_TYPE_TO_BIBLE_LEVELS' in ln)
    lang_decl = next(i for i, ln in enumerate(src_lines) if 'const LANGUAGE_TO_BIBLE_LEVELS' in ln)
    # Closing '};' of the LANGUAGE block = the first '};' line after lang_decl.
    lang_end = next(i for i, ln in enumerate(src_lines) if i > lang_decl and ln.strip() == '};')
    node_lines = {}
    lang_lines = {}
    for i, ln in enumerate(src_lines):
        m = re.match(r'^(\s*)(\w+):\s*\[', ln)
        if not m:
            continue
        if node_decl < i < lang_decl:
            node_lines[m.group(2)] = i
        elif lang_decl < i < lang_end:
            lang_lines[m.group(2)] = i

    # Build per-category curated id lists (first N by id, deterministic).
    node_curated = {}
    for cat, node_types in CATEGORY_TO_NODE_TYPES.items():
        ids = sorted(c['id'] for c in chunks if c.get('category') == cat)
        node_curated[cat] = ids[:MAX_NODE_PER_CATEGORY]
    lang_curated = {}
    for cat, langs in CATEGORY_TO_LANGS.items():
        ids = sorted(c['id'] for c in chunks if c.get('category') == cat)
        lang_curated[cat] = ids[:MAX_LANG_PER_CATEGORY]

    for cat, node_types in CATEGORY_TO_NODE_TYPES.items():
        ids = node_curated[cat]
        if not ids:
            continue
        for nt in node_types:
            if nt not in node_lines:
                print(f'  ! node type {nt} block not found — skipping')
                continue
            i = node_lines[nt]
            src_lines[i] = strip_new_ids(src_lines[i])
            src_lines[i] = append_curated(src_lines[i], ids)
            if not dry:
                print(f'  NODE {nt}: curated +{len(ids)} ids from {cat}')

    for cat, langs in CATEGORY_TO_LANGS.items():
        ids = lang_curated[cat]
        if not ids:
            continue
        for lang in langs:
            if lang not in lang_lines:
                print(f'  ! language {lang} block not found — skipping')
                continue
            i = lang_lines[lang]
            src_lines[i] = strip_new_ids(src_lines[i])
            src_lines[i] = append_curated(src_lines[i], ids)
            if not dry:
                print(f'  LANG {lang}: curated +{len(ids)} ids from {cat}')

    src = '\n'.join(src_lines)

    if dry:
        print('DRY RUN — no changes written')
    else:
        with open(TS, 'w', encoding='utf-8') as f:
            f.write(src)
        print('Wrote', os.path.relpath(TS, ROOT))
        # verify round-trip: scaffold can still parse it
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'scaffold-bible-curriculum.py'), '--dry-run'],
                           cwd=ROOT, capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-4:] if r.stdout else r.stderr.strip().splitlines()[-4:])


if __name__ == '__main__':
    main()
