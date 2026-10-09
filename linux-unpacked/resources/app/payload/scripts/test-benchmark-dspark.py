#!/usr/bin/env python3
"""
Unit tests for the pure helpers in scripts/benchmark-dspark.py:

  * historical_baseline()  — the baseline-cache protection (a lone smoke-test
    artifact line can never clobber the real pre-training stock baseline)
  * write_report()         — carries forward hand-added annotation keys
    (model_identity + nested corrected_mean/corrected_source) across runs
  * read_tuned_target()    — parses scripts/dspark-target.env
  * dspark_serves()        — verifies the served GGUF via process cmdline

Run:  python3 scripts/test-benchmark-dspark.py
Exit 0 = all pass, 1 = failures. No pytest dependency — matches the repo's
self-contained scripts/test-*.py convention (see scripts/test-import-path-fix.py).

The scenarios here are the regression cases from production incidents:
  - Aug 2026: a 3-token smoke test (~5.2 tok/s) in a freshly restarted
    dspark.log overwrote data/historical-stock-baseline.json, destroying the
    real pre-training 47.55 stock baseline (historical_baseline).
  - Aug 2026: benchmark-dspark.py json.dump'd the whole report each run,
    wiping hand-added annotation keys (model_identity, corrected_mean) until
    write_report() learned to carry them forward.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# --- load the module under test ------------------------------------------
_BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'benchmark-dspark.py')
_spec = importlib.util.spec_from_file_location('benchmark_dspark', _BENCH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_results = []


def check(name, cond, detail=''):
    _results.append(cond)
    print(('PASS' if cond else 'FAIL'), name, detail)


# --- helpers ---------------------------------------------------------------

def run_baseline(log_lines, cache=None, cache_raw=None):
    """Run historical_baseline() against an isolated temp SCRIPTS dir + cache."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'dspark.log').write_text('\n'.join(log_lines) + ('\n' if log_lines else ''))
        cachef = d / 'cache.json'
        if cache_raw is not None:
            cachef.write_text(cache_raw)
        elif cache is not None:
            cachef.write_text(json.dumps(cache))
        mod.SCRIPTS = str(d)
        mod.BASELINE_CACHE = str(cachef)
        res = mod.historical_baseline()
        cache_now = None
        if cachef.exists():
            try:
                cache_now = json.loads(cachef.read_text())
            except Exception:
                cache_now = None  # malformed cache — the scenario under test
        return res, cache_now


def run_write_report(prev_raw=None, fresh=None):
    """Run write_report() against an isolated temp REPORT_JSON."""
    with tempfile.TemporaryDirectory() as td:
        rf = Path(td) / 'report.json'
        mod.REPORT_JSON = str(rf)
        if prev_raw is not None:
            rf.write_text(prev_raw)
        mod.write_report(fresh)
        return json.loads(rf.read_text())


def run_tuned_target(content=None, exists=True):
    """Run read_tuned_target() against an isolated temp env file."""
    with tempfile.TemporaryDirectory() as td:
        ef = Path(td) / 'dspark-target.env'
        if exists:
            ef.write_text(content or '')
        mod.ENV_FILE = str(ef)
        return mod.read_tuned_target()


class _FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout


def run_serves(basename, pgrep_stdout):
    """Run dspark_serves() with subprocess.run mocked to return pgrep_stdout."""
    orig = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: _FakeProc(pgrep_stdout)
    try:
        return mod.dspark_serves(basename)
    finally:
        mod.subprocess.run = orig


# --- historical_baseline -----------------------------------------------------

# THE incident: 1-sample 5.2 artifact vs cached 47.55 -> rejected, cache kept.
res, cw = run_baseline(['[DSpark] chat: 3 tokens in 0.58s (5.2 tok/s)'],
                       cache={'last_measured': [47.2, 47.6, 47.8, 47.3, 47.7, 47.7], 'mean': 47.55})
check('baseline: 1-sample artifact rejected, cached mean kept',
      res['mean'] == 47.55 and 'fresh_rejected' in res)
check('baseline: artifact rejection leaves cache file untouched',
      cw is not None and cw['mean'] == 47.55)

# 3 plausible samples -> cache replaced (mean 47.53 is within 0.5x-2.0x).
res, cw = run_baseline(['[DSpark] chat: 200 tokens in 4.2s (47.2 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (47.6 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (47.8 tok/s)'],
                       cache={'last_measured': [47.55], 'mean': 47.55})
check('baseline: 3 plausible samples replace cache', res['mean'] == 47.53 and cw['mean'] == 47.53)

# 3 wild outliers -> rejected, cache kept.
res, cw = run_baseline(['[DSpark] chat: 200 tokens in 1.5s (120 tok/s)',
                        '[DSpark] chat: 200 tokens in 1.5s (130 tok/s)',
                        '[DSpark] chat: 200 tokens in 1.5s (140 tok/s)'],
                       cache={'last_measured': [47.55], 'mean': 47.55})
check('baseline: 3 wild outliers rejected, cached mean kept',
      res['mean'] == 47.55 and 'fresh_rejected' in res and cw['mean'] == 47.55)

# 1 sample, no cache -> unverified, NOT persisted.
res, cw = run_baseline(['[DSpark] chat: 3 tokens in 0.58s (5.2 tok/s)'])
check('baseline: 1 sample with no cache -> unverified, not persisted',
      'unverified' in res['source'] and cw is None)

# 3 samples, no cache -> seeds the cache (first-ever baseline).
res, cw = run_baseline(['[DSpark] chat: 200 tokens in 4.2s (47.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (48.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (49.0 tok/s)'])
check('baseline: 3 samples with no cache seed the cache',
      res['mean'] == 48.0 and cw is not None and cw['mean'] == 48.0)

# No log lines, cache present -> cached fallback.
res, cw = run_baseline([], cache={'last_measured': [47.55], 'mean': 47.55})
check('baseline: no log lines, cache present -> cached fallback',
      res['mean'] == 47.55 and 'cached' in res['source'])

# No log lines, no cache -> empty result, no crash.
res, cw = run_baseline([])
check('baseline: no log lines, no cache -> mean None, no crash',
      res['mean'] is None and cw is None)

# Non-dict cache (list) -> treated as no record, fresh 3-sample seeds cache.
res, cw = run_baseline(['[DSpark] chat: 200 tokens in 4.2s (47.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (48.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (49.0 tok/s)'],
                       cache_raw='["not", "a", "dict"]')
check('baseline: non-dict cache does not crash, seeds fresh cache',
      res['mean'] == 48.0 and cw is not None and cw['mean'] == 48.0)

# Malformed cache JSON -> no crash, unverified path.
res, cw = run_baseline(['[DSpark] chat: 3 tokens in 0.58s (5.2 tok/s)'],
                       cache_raw='{not json')
check('baseline: malformed cache JSON does not crash', 'unverified' in res['source'])

# Null cache + 3 samples -> no crash, seeds fresh cache.
res, cw = run_baseline(['[DSpark] chat: 200 tokens in 4.2s (47.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (48.0 tok/s)',
                        '[DSpark] chat: 200 tokens in 4.2s (49.0 tok/s)'],
                       cache_raw='null')
check('baseline: null cache does not crash, seeds fresh cache',
      res['mean'] == 48.0 and cw is not None and cw['mean'] == 48.0)


# --- write_report -------------------------------------------------------------

# Top-level model_identity + nested corrected_mean carried forward; fresh wins.
prev = {'timestamp': 'old', 'mode': 'now',
        'steps': {'before_deploy_historical': {'mean': 5.2, 'corrected_mean': 47.55,
                                               'corrected_source': 'data/historical-stock-baseline.json'}},
        'model_identity': {'tuned_gguf': 'X', 'verdict': 'tuned'}}
fresh = {'timestamp': 'new', 'mode': 'wait',
         'steps': {'before_deploy_historical': {'mean': 47.55, 'source': 'x'}}}
out = run_write_report(prev_raw=json.dumps(prev), fresh=fresh)
check('write_report: model_identity preserved', out.get('model_identity', {}).get('verdict') == 'tuned')
check('write_report: nested corrected_mean preserved',
      out['steps']['before_deploy_historical'].get('corrected_mean') == 47.55)
check('write_report: nested corrected_source preserved',
      'corrected_source' in out['steps']['before_deploy_historical'])
check('write_report: fresh script keys win',
      out['timestamp'] == 'new' and out['mode'] == 'wait')
check('write_report: fresh steps.mean untouched',
      out['steps']['before_deploy_historical']['mean'] == 47.55)

# Fresh run WITH its own corrected_mean -> stale value NOT resurrected.
fresh2 = {'timestamp': 't', 'mode': 'now',
          'steps': {'before_deploy_historical': {'mean': 60.0, 'corrected_mean': 60.0}}}
out2 = run_write_report(prev_raw=json.dumps(prev), fresh=fresh2)
check('write_report: fresh corrected_mean wins over stale',
      out2['steps']['before_deploy_historical']['corrected_mean'] == 60.0)
check('write_report: model_identity still carried forward',
      out2.get('model_identity', {}).get('verdict') == 'tuned')

# No previous report -> fresh, no crash, no carried keys.
out3 = run_write_report(fresh={'timestamp': 't', 'mode': 'now',
                               'steps': {'before_deploy_historical': {'mean': 1.0}}})
check('write_report: no prev -> fresh, no crash',
      out3['steps']['before_deploy_historical']['mean'] == 1.0 and 'model_identity' not in out3)

# Corrupt previous report -> no crash, fresh written.
out4 = run_write_report(prev_raw='{not json',
                        fresh={'timestamp': 't', 'mode': 'now', 'steps': {}})
check('write_report: corrupt prev JSON -> no crash, fresh written', out4['mode'] == 'now')

# Prev steps-as-list -> no crash; top-level still carried; nested skipped.
prev5 = {'timestamp': 'old', 'mode': 'now', 'steps': ['not', 'a', 'dict'],
         'model_identity': {'v': 1}}
out5 = run_write_report(prev_raw=json.dumps(prev5),
                        fresh={'timestamp': 't', 'mode': 'now',
                               'steps': {'before_deploy_historical': {'mean': 3.0}}})
check('write_report: prev steps-as-list -> no crash',
      out5['steps']['before_deploy_historical']['mean'] == 3.0)
check('write_report: prev steps-as-list -> top-level still carried',
      out5.get('model_identity', {}).get('v') == 1)

# Prev bdh-as-list -> no crash; top-level still carried.
prev6 = {'timestamp': 'old', 'mode': 'now',
         'steps': {'before_deploy_historical': ['x']}, 'model_identity': {'v': 2}}
out6 = run_write_report(prev_raw=json.dumps(prev6),
                        fresh={'timestamp': 't', 'mode': 'now',
                               'steps': {'before_deploy_historical': {'mean': 4.0}}})
check('write_report: prev bdh-as-list -> no crash',
      out6['steps']['before_deploy_historical']['mean'] == 4.0)
check('write_report: prev bdh-as-list -> top-level still carried',
      out6.get('model_identity', {}).get('v') == 2)

# Clean nested carry-forward from a dict prev.
prev7 = {'timestamp': 'old', 'mode': 'now',
         'steps': {'before_deploy_historical': {'corrected_mean': 47.55,
                                                'corrected_source': 'src'}},
         'model_identity': {'v': 3}}
out7 = run_write_report(prev_raw=json.dumps(prev7),
                        fresh={'timestamp': 't', 'mode': 'now',
                               'steps': {'before_deploy_historical': {'mean': 5.0}}})
check('write_report: nested dict carry-forward works',
      out7['steps']['before_deploy_historical'].get('corrected_mean') == 47.55)
check('write_report: carried model_identity v3', out7.get('model_identity', {}).get('v') == 3)


# --- read_tuned_target --------------------------------------------------------

check('tuned_target: parses DSPARK_TARGET value',
      run_tuned_target('DSPARK_TARGET=/models/tuned.gguf\n') == '/models/tuned.gguf')
check('tuned_target: strips trailing whitespace',
      run_tuned_target('DSPARK_TARGET=/models/tuned.gguf   ') == '/models/tuned.gguf')
check('tuned_target: missing env file -> empty', run_tuned_target(exists=False) == '')
check('tuned_target: file without DSPARK_TARGET -> empty',
      run_tuned_target('FOO=bar\nBAZ=1\n') == '')


# --- dspark_serves -------------------------------------------------------------

check('serves: empty basename -> True', run_serves('', '') is True)
check('serves: matching --target -> True',
      run_serves('Qwen2.5-7B-Instruct-Uncensored.Q4_K_M.gguf',
                 '123 python scripts/dspark_server.py --target /models/Qwen2.5-7B-Instruct-Uncensored.Q4_K_M.gguf') is True)
check('serves: non-matching target -> False',
      run_serves('stock.gguf', '123 python scripts/dspark_server.py --target /models/tuned.gguf') is False)

# Real exception path: mock subprocess.run to raise, expect graceful False.
_orig_run = mod.subprocess.run
mod.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom'))
try:
    _serves_exc = mod.dspark_serves('anything.gguf')
finally:
    mod.subprocess.run = _orig_run
check('serves: subprocess raises -> False (no crash)', _serves_exc is False)


# --- summary -------------------------------------------------------------------

print('---')
failed = len([c for c in _results if not c])
print(f'RESULT: {len(_results) - failed}/{len(_results)} passed')
sys.exit(1 if failed else 0)
