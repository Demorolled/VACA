#!/usr/bin/env python3
"""Determine how many bible-reference md files contain REAL implementations."""
import importlib.util
import os
import re

spec = importlib.util.spec_from_file_location('g', 'scripts/build-new-bible-patterns.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def is_real_impl(code):
    """Heuristic: an implementation has actual statements, not just a signature."""
    if len(code) < 250:
        return False
    # real bodies have '=> {' or 'function ... {' or 'return ' or assignments
    if 'return ' in code and '{' in code:
        return True
    if '=>' in code and '{' in code:
        return True
    if re.search(r'\b(function|class)\b', code) and '{' in code:
        return True
    return False


chunks = g.new_chunks()
real = [c for c in chunks if is_real_impl(c['code'])]
print('new chunks:', len(chunks))
print('chunks with REAL implementations:', len(real))
print('chunks with stubs/signatures:', len(chunks) - len(real))

# sample real ones
for c in real[:4]:
    print('\n---', c['path'], '| when:', c['when'][:60])
    print(c['code'][:600].replace('\n', ' | '))
