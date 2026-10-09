#!/usr/bin/env python3
"""
Validate blueprint-JSON contract fidelity of the model serving on port 8000
===========================================================================
Sends held-out prompts (training/dataset/blueprint-pairs-test.jsonl, or a
sampled subset) to the live dspark OpenAI-compatible endpoint and checks each
response against the engine's strict Blueprint contract (bible.ts):

    Blueprint {
      app_type: string;
      description: string;
      keywords: string[];
      target_stack: { frontend, backend, database: string };
      architecture_checklist: string[];
      wiring_graph: { source_module, destination_module, data_passed: string }[];
    }

Checks (in order, each blocks the next):
  1. parse    — response parses as JSON (with markdown-fence tolerance)
  2. keys     — all 6 CONTRACT_KEYS present
  3. types    — keywords/checklist/wiring are arrays; target_stack has 3 string fields
  4. known    — app_type exists in the real blueprint library (backend/blueprints/**)
  5. exact    — app_type matches the expected blueprint from the dataset
  6. fidelity — full structural fidelity vs the expected output (app_type +
                checklist length + wiring length + stack values)

Reports a summary + per-case detail, and writes a JSON report to
data/blueprint-fidelity-validation.json.

Usage:
  python3 scripts/validate-blueprint-fidelity.py [--limit 20] [--seed 42]
  python3 scripts/validate-blueprint-fidelity.py --all      # all 61 test prompts
"""

import argparse
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSPARK_URL = 'http://127.0.0.1:8000/v1/chat/completions'
DSPARK_MODEL = 'default'
TEST_FILE = os.path.join(BASE, 'training', 'dataset', 'blueprint-pairs-test.jsonl')
REPORT_FILE = os.path.join(BASE, 'data', 'blueprint-fidelity-validation.json')
BLUEPRINT_DIRS = [
    os.path.join(BASE, 'backend', 'blueprints', '**', '*.json'),
]

CONTRACT_KEYS = ('app_type', 'description', 'keywords', 'target_stack',
                 'architecture_checklist', 'wiring_graph')
TARGET_STACK_KEYS = ('frontend', 'backend', 'database')
WIRING_KEYS = ('source_module', 'destination_module', 'data_passed')

MAX_TOKENS = 1024
TEMPERATURE = 0.2
REQUEST_TIMEOUT = 180


# ─── Blueprint library ─────────────────────────────────────────────────────

def load_blueprint_library() -> dict:
    """app_type -> blueprint for every blueprint the engine actually serves."""
    bps = {}
    for pat in BLUEPRINT_DIRS:
        for p in __import__('glob').glob(pat):
            try:
                with open(p, encoding='utf-8') as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(raw, dict) and isinstance(raw.get('app_type'), str):
                bps[raw['app_type'].strip()] = raw
    return bps


# ─── HTTP ──────────────────────────────────────────────────────────────────

def chat(content: str) -> str:
    payload = {
        'model': DSPARK_MODEL,
        'messages': [{'role': 'user', 'content': content}],
        'max_tokens': MAX_TOKENS,
        'temperature': TEMPERATURE,
        'stream': False,
    }
    req = urllib.request.Request(
        DSPARK_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.load(resp)
    return data['choices'][0]['message']['content']


# ─── Validation ────────────────────────────────────────────────────────────

def extract_json(text: str):
    """Parse model output as JSON. Tolerates markdown fences and leading prose."""
    text = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: extract the outermost {...} span.
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def validate(parsed, expected: dict, library: dict) -> dict:
    """Return {ok, checks: {...}} — each check True/False (checked in order)."""
    checks = {'parse': parsed is not None}
    if not checks['parse']:
        return {'ok': False, 'checks': checks}

    keys_ok = isinstance(parsed, dict) and all(k in parsed for k in CONTRACT_KEYS)
    checks['keys'] = keys_ok
    if not keys_ok:
        return {'ok': False, 'checks': checks}

    ts = parsed.get('target_stack') or {}
    types_ok = (
        isinstance(parsed.get('keywords'), list)
        and isinstance(parsed.get('architecture_checklist'), list)
        and isinstance(parsed.get('wiring_graph'), list)
        and isinstance(ts, dict)
        and all(k in ts for k in TARGET_STACK_KEYS)
    )
    checks['types'] = types_ok
    if not types_ok:
        return {'ok': False, 'checks': checks}

    app_type = parsed.get('app_type')
    checks['known'] = app_type in library
    if not checks['known']:
        return {'ok': False, 'checks': checks}

    checks['exact'] = app_type == expected.get('app_type')
    # Fidelity vs expected: same stack, checklist length, wiring length.
    exp = expected or {}
    exp_ts = exp.get('target_stack') or {}
    checks['fidelity'] = (
        checks['exact']
        and ts.get('frontend') == exp_ts.get('frontend')
        and ts.get('backend') == exp_ts.get('backend')
        and ts.get('database') == exp_ts.get('database')
        and len(parsed.get('architecture_checklist') or []) == len(exp.get('architecture_checklist') or [])
        and len(parsed.get('wiring_graph') or []) == len(exp.get('wiring_graph') or [])
    )
    return {'ok': all(checks.values()), 'checks': checks}


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=15,
                    help='sample size (default 15); ignored with --all')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--all', action='store_true', help='run all test prompts')
    args = ap.parse_args()

    if not os.path.exists(TEST_FILE):
        print(f'❌ Test file not found: {TEST_FILE}')
        sys.exit(1)

    with open(TEST_FILE, encoding='utf-8') as f:
        records = [json.loads(l) for l in f if l.strip()]
    rng = random.Random(args.seed)
    sample = records if args.all else rng.sample(records, min(args.limit, len(records)))
    print(f'[fidelity] {len(sample)} prompts -> {DSPARK_URL} (temp {TEMPERATURE}, max_tok {MAX_TOKENS})')

    library = load_blueprint_library()
    print(f'[fidelity] blueprint library: {len(library)} app types loaded')

    results = []
    for i, rec in enumerate(sample, 1):
        instruction = rec.get('instruction', '')
        try:
            expected = json.loads(rec.get('output', '{}'))
        except json.JSONDecodeError:
            expected = {}
        t0 = time.time()
        try:
            raw = chat(instruction)
            parsed = extract_json(raw)
            verdict = validate(parsed, expected, library)
            elapsed = time.time() - t0
            app_type = parsed.get('app_type') if isinstance(parsed, dict) else None
            status = '✅' if verdict['ok'] else '❌'
            print(f'  {status} [{i}/{len(sample)}] {app_type or "<no json>"} '
                  f'({"|".join("✓" if v else "✗" for k, v in verdict["checks"].items())}) '
                  f'{elapsed:.1f}s')
            results.append({
                'instruction': instruction[:200],
                'expected_app_type': expected.get('app_type'),
                'got_app_type': app_type,
                'checks': verdict['checks'],
                'ok': verdict['ok'],
                'elapsed_s': round(elapsed, 2),
                'output_preview': (raw or '')[:500],
            })
        except Exception as e:
            print(f'  ❌ [{i}/{len(sample)}] request failed: {e}')
            results.append({
                'instruction': instruction[:200],
                'expected_app_type': expected.get('app_type'),
                'got_app_type': None,
                'checks': {'parse': False, 'request_error': str(e)},
                'ok': False,
                'elapsed_s': None,
                'output_preview': '',
            })

    n = len(results)
    if n == 0:
        print('[fidelity] no results!')
        sys.exit(1)

    def rate(key):
        return sum(1 for r in results if r.get('checks', {}).get(key)) / n

    summary = {
        'generated': datetime.datetime.now().isoformat(timespec='seconds'),
        'endpoint': DSPARK_URL,
        'samples': n,
        'temperature': TEMPERATURE,
        'parse_rate_pct': round(100 * rate('parse'), 1),
        'keys_rate_pct': round(100 * rate('keys'), 1),
        'types_rate_pct': round(100 * rate('types'), 1),
        'known_app_type_rate_pct': round(100 * rate('known'), 1),
        'exact_app_type_rate_pct': round(100 * rate('exact'), 1),
        'full_fidelity_rate_pct': round(100 * rate('fidelity'), 1),
        'overall_ok_rate_pct': round(100 * sum(1 for r in results if r['ok']) / n, 1),
        'cases': results,
    }

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f'\n{f"═" * 52}')
    print(f'  BLUEPRINT CONTRACT-FIDELITY REPORT  ({n} prompts)')
    print(f'{"═" * 52}')
    print(f'  Parses as JSON           : {summary["parse_rate_pct"]}%')
    print(f'  All 6 contract keys      : {summary["keys_rate_pct"]}%')
    print(f'  Correct types            : {summary["types_rate_pct"]}%')
    print(f'  Known app_type           : {summary["known_app_type_rate_pct"]}%')
    print(f'  Exact expected app_type  : {summary["exact_app_type_rate_pct"]}%')
    print(f'  Full structural fidelity : {summary["full_fidelity_rate_pct"]}%')
    print(f'  OVERALL OK               : {summary["overall_ok_rate_pct"]}%')
    print(f'{"═" * 52}')
    print(f'[fidelity] report -> {REPORT_FILE}')


if __name__ == '__main__':
    main()
