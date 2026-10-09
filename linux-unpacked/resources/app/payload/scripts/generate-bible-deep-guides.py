#!/usr/bin/env python3
"""
Generate deep technical guides for the bible-reference/ curriculum via DSpark.
==============================================================================

Phase 2 of the bible-reference restoration: the scaffold script created the
level tree (MASTER-INDEX.txt + 00-index.md per level) from BIBLE_LEVEL_TOPICS.
This script writes a REAL deep guide per level by calling the local DSpark
server (OpenAI-compatible, http://127.0.0.1:8000/v1) and saves it as
`bible-reference/<level>/01-deep-guide.md` (the loader only reads 00-index.*,
so the deep guide is browsable via /api/library/bible/:level/:filename without
changing the injected context size).

Contract:
  * Reads level names + topics from the scaffolded 00-index.md files.
  * Skips levels that already have a deep guide (--force to overwrite).
  * Never fails the run: per-level errors are logged and skipped.
  * --levels "01-foundations,02-games" restricts to a subset; --dry-run prints
    the prompts without calling the model.

Usage:
  python3 scripts/generate-bible-deep-guides.py [--levels "a,b"] [--force]
        [--dry-run] [--max-tokens 4096] [--out DIR]
"""
import os
import re
import sys
import json
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, 'bible-reference')
DSPARK_URL = 'http://127.0.0.1:8000/v1/chat/completions'
DSPARK_MODEL = 'qwen2.5-7b-instruct-uncensored-dspark'
REQUEST_TIMEOUT = 600          # deep guides can be slow on the 7B
MAX_TOKENS = 4096
TEMPERATURE = 0.6

SYSTEM_PROMPT = (
    'You are the author of "The Programming Bible", a deep technical reference '
    'curriculum used by an AI app-builder to steer code generation. You write '
    'accurate, dense, practical guides in Markdown. Use headings, bullet lists, '
    'short code examples, and concrete best practices. Avoid fluff, disclaimers, '
    'and meta-commentary. Target roughly 150-250 lines per guide.'
)

USER_TEMPLATE = """Write a deep technical guide for Bible level {title}.

Level topics to cover: {topics}

Required structure:
# {title} — Deep Technical Guide
## Overview
## Core Concepts
## Key Patterns & Architectures
## Implementation Guidance (with short code examples)
## Common Pitfalls
## Best Practices Checklist
## Related Topics

Keep it practical and dense — this will be used as a reference by an LLM code generator."""


def read_levels(out_dir: str):
    """Return [{level, title, topics, index_path}] from scaffolded 00-index.md files."""
    levels = []
    for entry in sorted(os.listdir(out_dir)):
        dir_path = os.path.join(out_dir, entry)
        if not os.path.isdir(dir_path):
            continue
        index = None
        for f in os.listdir(dir_path):
            if f.startswith('00-index.'):
                index = os.path.join(dir_path, f)
                break
        if not index:
            continue
        content = open(index, encoding='utf-8').read()
        m = re.search(r'^# (.+)$', content, re.M)
        title = m.group(1).strip() if m else entry
        topics_m = re.search(r'^Level topics: (.+?)\.', content, re.M)
        topics = topics_m.group(1).strip() if topics_m else ''
        levels.append({'level': entry, 'title': title, 'topics': topics, 'index_path': index})
    return levels


def call_dspark(user_prompt: str) -> str:
    payload = {
        'model': DSPARK_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': MAX_TOKENS,
        'temperature': TEMPERATURE,
        'stream': False,
    }
    req = urllib.request.Request(
        DSPARK_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer dspark'},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content'].strip()


def main():
    args = sys.argv[1:]
    out_dir = DEFAULT_OUT
    if '--out' in args:
        out_dir = args[args.index('--out') + 1]
    force = '--force' in args
    dry_run = '--dry-run' in args
    levels_filter = None
    if '--levels' in args:
        levels_filter = {s.strip() for s in args[args.index('--levels') + 1].split(',') if s.strip()}

    if not os.path.isdir(out_dir):
        raise SystemExit(f'No curriculum at {out_dir} — run scripts/scaffold-bible-curriculum.py first.')

    levels = read_levels(out_dir)
    if levels_filter:
        levels = [l for l in levels if l['level'] in levels_filter]
    if not levels:
        raise SystemExit('No matching levels found.')

    ok = skipped = failed = 0
    for i, lvl in enumerate(levels, 1):
        guide_path = os.path.join(out_dir, lvl['level'], '01-deep-guide.md')
        if os.path.exists(guide_path) and not force:
            print(f'[{i}/{len(levels)}] ⏭  {lvl["level"]} — guide exists, skipping (--force to overwrite)')
            skipped += 1
            continue

        prompt = USER_TEMPLATE.format(title=lvl['title'], topics=lvl['topics'])
        if dry_run:
            print(f'[{i}/{len(levels)}] [dry-run] would write {os.path.relpath(guide_path, ROOT)}')
            ok += 1
            continue

        print(f'[{i}/{len(levels)}] ✍️  {lvl["level"]} — {lvl["title"]} (topics: {lvl["topics"][:80]}...)', flush=True)
        try:
            guide = call_dspark(prompt)
            if not guide or len(guide) < 200:
                raise ValueError(f'suspiciously short guide ({len(guide)} chars)')
            with open(guide_path, 'w', encoding='utf-8') as f:
                f.write(guide + '\n')
            ok += 1
            print(f'      ✅ wrote {len(guide)} chars → {os.path.relpath(guide_path, ROOT)}')
        except Exception as err:
            failed += 1
            print(f'      ❌ failed: {err}')
        time.sleep(0.5)  # be polite to the local server

    print(f'\nDone: {ok} written, {skipped} skipped, {failed} failed.')


if __name__ == '__main__':
    main()
