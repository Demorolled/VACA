#!/usr/bin/env python3
"""Probe round-8 teacher throughput: 1 vs 2 parallel requests to qwen3.6:27b."""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MODEL = 'qwen3.6:27b-q4_K_M'
BASE = 'http://127.0.0.1:11434'

def ask(q, timeout=180):
    body = json.dumps({
        'model': MODEL, 'stream': False, 'think': False,
        'messages': [{'role': 'user', 'content': q}],
        'options': {'temperature': 0.7, 'num_predict': 300},
    }).encode()
    req = urllib.request.Request(BASE + '/api/chat', data=body,
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    dt = time.time() - t0
    content = (d.get('message', {}).get('content') or '').strip()
    return dt, d.get('eval_count', 0), content

QUESTS = [
    'Write a Python function to flatten a nested list. Tight, to the point.',
    'Write a JS function that debounces another function. Tight.',
    'Write a SQL query to find duplicate emails in a users table. Tight.',
]

def run_parallel(n):
    results = []
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(ask, q) for q in QUESTS]
        for f in futs:
            results.append(f.result())
    return results

for n in (1, 2):
    t0 = time.time()
    results = run_parallel(n)
    wall = time.time() - t0
    tot_tok = sum(r[1] for r in results)
    print(f'--- parallel={n} ---')
    for i, (dt, tok, content) in enumerate(results):
        print(f'  req{i}: {tok} tok in {dt:.1f}s ({tok/max(dt,0.001):.1f} tok/s) | first 60: {content[:60]!r}')
    print(f'  aggregate: {tot_tok} tok in {wall:.1f}s = {tot_tok/wall:.1f} tok/s wall\n')
