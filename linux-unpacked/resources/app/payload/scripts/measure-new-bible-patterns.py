#!/usr/bin/env python3
"""Measure how many genuinely-new code chunks exist in bible-reference/*.md
versus the 904 existing data/code-bible chunks. Also check the existing
round-6 bible rows so the new 1,000 patterns are guaranteed non-repeats."""
import hashlib
import importlib.util
import json
import os
import re

ROOT = '/home/final-flash1/Desktop/visual-ai-architect'
CHUNK_DB = os.path.join(ROOT, 'data', 'code-bible')
BIBLE = os.path.join(ROOT, 'bible-reference')


def code_hash(code):
    # normalize whitespace so equivalent code blocks hash the same
    norm = re.sub(r'\s+', ' ', code).strip()
    return hashlib.sha1(norm.encode()).hexdigest()


def load_existing_chunks():
    chunks = []
    for fn in sorted(os.listdir(CHUNK_DB)):
        if not fn.endswith('.py'):
            continue
        spec = importlib.util.spec_from_file_location('c_' + fn[:-3], os.path.join(CHUNK_DB, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        chunks.extend(getattr(mod, 'CHUNKS', []))
    return chunks


def parse_md(path):
    """Parse an atomic-component md into {name, when, iface, code, tags}."""
    text = open(path, encoding='utf-8', errors='ignore').read()
    out = {'path': os.path.relpath(path, BIBLE), 'name': '', 'when': '',
           'tags': [], 'code_blocks': 0, 'code': ''}
    # title line: "# slug — Name"
    m2 = re.search(r'^#\s+(.+?)\s*—\s*(.+)$', text, re.M)
    if m2:
        out['name'] = m2.group(2).strip()
    else:
        m3 = re.search(r'^#\s+(.+)$', text, re.M)
        if m3:
            out['name'] = m3.group(1).strip()
    # when-to-use section
    m = re.search(r'## When to Use\s*\n+(.*?)(?=\n## |\Z)', text, re.S)
    if m:
        body = m.group(1).strip()
        # strip the **Why:** line
        body = re.sub(r'\*\*Why:\*\*.*', '', body, flags=re.S).strip()
        out['when'] = re.sub(r'\s+', ' ', body).strip()
    # tags
    tags = re.findall(r'`([a-z][\w\-]*)`', text)
    out['tags'] = [t for t in tags[:12]]
    # code blocks: last ```lang ... ``` block is usually the implementation
    blocks = re.findall(r'```(?:ts|typescript|py|python|go|rs|rust|c|cpp|sh|bash|js)?\s*\n(.*?)```', text, re.S)
    out['code_blocks'] = len(blocks)
    out['code'] = blocks[-1].strip() if blocks else ''
    return out


def main():
    existing = load_existing_chunks()
    print('existing code-bible chunks:', len(existing))
    existing_hashes = set()
    for c in existing:
        if c.get('code'):
            existing_hashes.add(code_hash(c['code']))
    print('existing code hashes:', len(existing_hashes))

    md_files = []
    for root, _, files in os.walk(BIBLE):
        for f in files:
            if f.endswith('.md'):
                md_files.append(os.path.join(root, f))
    print('md files:', len(md_files))

    new_chunks = []
    dup_chunks = 0
    no_code = 0
    no_when = 0
    for p in md_files:
        c = parse_md(p)
        if not c['code']:
            no_code += 1
            continue
        h = code_hash(c['code'])
        if h in existing_hashes:
            dup_chunks += 1
            continue
        if not c['when'] or not c['name']:
            no_when += 1
            continue
        new_chunks.append(c)
    print('dup vs existing chunks:', dup_chunks)
    print('no code block:', no_code)
    print('no when/name:', no_when)
    print('GENUINELY NEW chunks:', len(new_chunks))

    # also check round-6 bible row dedupe keys (instruction) we must avoid
    r6 = os.path.join(ROOT, 'training', 'dataset', 'round6-bible-10h.jsonl')
    r6_instr = set()
    with open(r6, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                r6_instr.add(json.loads(line).get('instruction', ''))
    print('round-6 rows:', len(r6_instr))

    # sample new chunks
    for c in new_chunks[:3]:
        print('\n---', c['path'], '|', c['name'])
        print('  when:', (c['when'] or '')[:120])
        print('  code:', (c['code'] or '')[:120].replace('\n', ' '))


if __name__ == '__main__':
    main()
