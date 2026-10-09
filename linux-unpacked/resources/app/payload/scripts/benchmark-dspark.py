#!/usr/bin/env python3
"""
Benchmark dspark: tuned vs stock tokens/sec + draft-mode verification.

Measures real-world generation throughput BEFORE and AFTER the tuned-GGUF
deploy, using the server's own /v1/health rolling-window stats (tokens_per_sec)
plus client-side timing, and verifies that speculative-decoding draft modes
still work with the tuned GGUF.

Before-deploy baseline:
  dspark is stopped during training, so the live "before" baseline is captured
  two ways:
    1. historical: the last measured tok/s values in scripts/dspark.log from the
       pre-training stock run (draft mode none, ~47 tok/s)
    2. control: after deploy, dspark is briefly pointed back at the stock GGUF,
       benchmarked on the SAME hardware, then restored to the tuned GGUF

After-deploy:
  - benchmark the tuned model (draft mode none, the deployed default)
  - restart with DSPARK_DRAFT_MODE=model (real drafter qwen2.5-coder:0.5b),
    verify /v1/health reports draft_mode=model & speculative_decoding=true,
    run a generation, confirm it works

Everything is restored afterwards: tuned target + default draft mode (none).

Usage:
  python3 scripts/benchmark-dspark.py --wait    # auto-run after deploy (default)
  python3 scripts/benchmark-dspark.py --now     # benchmark whatever dspark serves now
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BASE, 'scripts')
DATA = os.path.join(BASE, 'data')
MODELS = os.path.join(BASE, 'models')
ENV_FILE = os.path.join(SCRIPTS, 'dspark-target.env')
DSPARK_URL = 'http://127.0.0.1:8000'
STOCK_GGUF = os.path.join(MODELS, 'qwen2.5-7b-instruct-uncensored-q4_k_m.gguf')
REPORT_JSON = os.path.join(DATA, 'benchmark-dspark.json')
REPORT_LOG = os.path.join(DATA, 'benchmark-dspark.log')

# Fixed prompt — a realistic GUI node codegen instruction (countdown engine),
# identical across all runs/models so throughput comparisons are apples-to-apples.
BENCH_PROMPT = (
    "Generate a TypeScript class CountdownEngine with start(), pause(), "
    "resume(), reset(), and a status getter. It ticks every second, fires "
    "an onTick callback with remaining seconds, stops at zero. No imports, "
    "no JSX, no markdown, plain TypeScript, named exports only."
)
NUM_RUNS = 3
MAX_TOKENS = 200
TEMPERATURE = 0.7


def log(msg: str):
    line = f"[bench] {datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(REPORT_LOG, 'a') as f:
        f.write(line + '\n')


def http_json(url: str, method: str = 'GET', payload=None, timeout: int = 600):
    req = urllib.request.Request(url, method=method)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, data=body, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_health():
    try:
        return http_json(DSPARK_URL + '/v1/health', timeout=5)
    except Exception:
        return None


def read_tuned_target() -> str:
    """Return the DSPARK_TARGET written by the deploy watcher (tuned GGUF)."""
    if not os.path.isfile(ENV_FILE):
        return ''
    with open(ENV_FILE) as f:
        m = re.search(r'DSPARK_TARGET=(.+)', f.read())
    return m.group(1).strip() if m else ''


BASELINE_CACHE = os.path.join(DATA, 'historical-stock-baseline.json')


def historical_baseline() -> dict:
    """Parse the last measured tok/s from the pre-training stock dspark.log.

    dspark.log is overwritten whenever dspark restarts (e.g. by this very
    benchmark's swap steps), so any captured values are also persisted to a
    cache file and used as a fallback on later runs — otherwise the
    before/after comparison would silently become null.

    The cache is only REPLACED when the fresh readings are trustworthy:
    at least 3 samples AND a mean that is plausible relative to the existing
    cached record (within 0.5x–2.0x). A lone artifact line (e.g. a 3-token
    smoke test at ~5 tok/s) can never clobber the real pre-training baseline.
    """
    logf = os.path.join(SCRIPTS, 'dspark.log')
    vals = []
    if os.path.isfile(logf):
        with open(logf, errors='ignore') as f:
            for line in f:
                m = re.search(r'\((\d+(?:\.\d+)?) tok/s', line)
                if m:
                    vals.append(float(m.group(1)))
    hist = vals[-6:] if vals else []

    # Load the existing record FIRST so fresh readings can be judged against it.
    # Guard against a non-dict cache (corrupt/hand-edited file) — fall back to
    # treating it as no record rather than crashing on .get().
    cached = {}
    if os.path.isfile(BASELINE_CACHE):
        try:
            with open(BASELINE_CACHE) as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                cached = parsed
        except Exception:
            cached = {}
    c_mean = cached.get('mean')

    if hist:
        mean = round(sum(hist) / len(hist), 2)
        # Trust the fresh log only with enough samples AND a plausible mean
        # relative to the record it would replace (0.5x–2.0x band).
        enough_samples = len(hist) >= 3
        plausible = True
        if c_mean:
            ratio = mean / c_mean if c_mean else 1.0
            plausible = 0.5 <= ratio <= 2.0
        if enough_samples and plausible:
            try:
                with open(BASELINE_CACHE, 'w') as f:
                    json.dump({'last_measured': hist, 'mean': mean}, f)
            except Exception:
                pass
            return {
                'source': logf,
                'last_measured': hist,
                'mean': mean,
            }
        # Fresh reading rejected as an outlier/artifact — keep the cached record.
        if c_mean is not None:
            return {
                'source': logf + f' (cached — fresh log rejected: {len(hist)} sample(s), mean {mean})',
                'last_measured': cached.get('last_measured', []),
                'mean': c_mean,
                'fresh_rejected': {'last_measured': hist, 'mean': mean},
            }
        # No record to keep — return the fresh reading (best-effort) WITHOUT
        # persisting it (too few samples / no reference to judge against).
        return {
            'source': logf + f' (unverified: {len(hist)} sample(s))',
            'last_measured': hist,
            'mean': mean,
        }

    # No live tok/s lines (log rotated/overwritten) — fall back to the cache.
    if c_mean is not None:
        return {
            'source': logf + ' (cached)',
            'last_measured': cached.get('last_measured', []),
            'mean': c_mean,
        }
    return {
        'source': logf,
        'last_measured': [],
        'mean': None,
    }


def dspark_serves(model_basename: str) -> bool:
    """True if the running dspark_server process was launched with this GGUF
    basename (via --target). /v1/health's 'model' field is a static friendly
    name (e.g. qwen2.5-7b-instruct-uncensored-dspark) — NOT the GGUF basename
    — so the process cmdline is the only reliable way to verify the target."""
    if not model_basename:
        return True
    try:
        out = subprocess.run(['pgrep', '-fa', 'dspark_server.py'],
                             capture_output=True, text=True).stdout
        # Parse the --target argument explicitly (avoids matching stray
        # processes whose cmdline merely contains the basename string).
        for line in out.splitlines():
            m = re.search(r'--target\s+(\S+)', line)
            if m and os.path.basename(m.group(1)) == model_basename:
                return True
        return False
    except Exception:
        return False


def wait_for_health(model_basename: str = '', timeout: int = 900) -> dict:
    """Poll /v1/health until ok, verifying the served GGUF via the process
    cmdline (health's model field is a static friendly name, not the basename)."""
    start = time.time()
    while time.time() - start < timeout:
        h = get_health()
        if h and h.get('status') == 'ok' and dspark_serves(model_basename):
            return h
        time.sleep(10)
    return None


def wait_ab_test_done(timeout: int = 1800) -> bool:
    """Wait for the A/B test harness to finish so we don't fight it over dspark."""
    start = time.time()
    while time.time() - start < timeout:
        out = subprocess.run(['pgrep', '-f', 'ab-test-tuned-vs-stock.py'],
                             capture_output=True, text=True).stdout.strip()
        if not out:
            return True
        time.sleep(15)
    log(f"WARNING: A/B test still running after {timeout}s — proceeding anyway")
    return False


def free_dspark_port():
    """Kill whatever holds tcp:8000, but ONLY if it is actually dspark."""
    pids = subprocess.run(['lsof', '-ti', 'tcp:8000'], capture_output=True,
                          text=True).stdout.strip()
    for pid in pids.split():
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                cmd = f.read().decode(errors='ignore').replace('\x00', ' ')
        except OSError:
            continue
        if 'dspark_server.py' in cmd:
            subprocess.run(['kill', '-9', pid], capture_output=True, timeout=15)
            log(f"  killed stale dspark pid {pid} on port 8000")
    time.sleep(2)


def restart_dspark(target: str, draft_mode: str) -> dict:
    """Stop dspark, start it with the given target + draft mode, wait for health."""
    log(f"restarting dspark: target={os.path.basename(target) if target else 'env'} "
        f"draft_mode={draft_mode}")
    subprocess.run(['bash', os.path.join(SCRIPTS, 'start-dspark.sh'), '--stop'],
                   cwd=BASE, capture_output=True, timeout=30)
    free_dspark_port()
    env = dict(os.environ)
    if target:
        env['DSPARK_TARGET'] = target
    env['DSPARK_DRAFT_MODE'] = draft_mode
    try:
        subprocess.run(['bash', os.path.join(SCRIPTS, 'start-dspark.sh'), '--background'],
                       cwd=BASE, env=env, capture_output=True, timeout=420)
    except subprocess.TimeoutExpired:
        log("WARNING: start-dspark.sh --background timed out (model load slow?)")
    return wait_for_health(model_basename=os.path.basename(target) if target else '',
                           timeout=300)


def benchmark(label: str, n_runs: int = NUM_RUNS) -> dict:
    """Run n identical generations, record client-side tps + server health stats."""
    runs = []
    for i in range(n_runs):
        payload = {
            'model': 'default',
            'messages': [{'role': 'user', 'content': BENCH_PROMPT}],
            'max_tokens': MAX_TOKENS,
            'temperature': TEMPERATURE,
            'stream': False,
        }
        t0 = time.time()
        try:
            resp = http_json(DSPARK_URL + '/v1/chat/completions', 'POST', payload, timeout=600)
            elapsed = time.time() - t0
            ct = resp.get('usage', {}).get('completion_tokens', 0)
            pt = resp.get('usage', {}).get('prompt_tokens', 0)
            tps = ct / elapsed if elapsed > 0 else 0.0
            runs.append({
                'completion_tokens': ct,
                'prompt_tokens': pt,
                'elapsed_s': round(elapsed, 3),
                'client_tps': round(tps, 2),
            })
            log(f"{label} run {i + 1}: {ct} tok in {elapsed:.2f}s = {tps:.1f} tok/s")
        except Exception as e:
            runs.append({'error': str(e)})
            log(f"{label} run {i + 1} FAILED: {e}")
        time.sleep(1)
    health = get_health()
    server_stats = (health or {}).get('stats') or {}
    ok_runs = [r['client_tps'] for r in runs if 'client_tps' in r]
    return {
        'runs': runs,
        'client_tps_mean': round(sum(ok_runs) / len(ok_runs), 2) if ok_runs else None,
        'health_stats': server_stats,
    }


def verify_draft_mode(tuned: str) -> dict:
    """Restart with the real drafter, verify health, run one generation."""
    log("--- draft-mode verification (DSPARK_DRAFT_MODE=model) ---")
    health = restart_dspark(target=tuned, draft_mode='model')
    if not health:
        log("FAIL: dspark did not come up in draft-mode model")
        return {'ok': False, 'error': 'dspark not healthy'}
    report = {
        'ok': health.get('draft_mode') == 'model' and health.get('speculative_decoding') is True,
        'health': {
            'model': health.get('model'),
            'draft_mode': health.get('draft_mode'),
            'speculative_decoding': health.get('speculative_decoding'),
            'draft': health.get('draft'),
        },
    }
    log(f"health: draft_mode={health.get('draft_mode')} "
        f"speculative_decoding={health.get('speculative_decoding')} "
        f"draft={health.get('draft')}")
    res = benchmark('tuned-draft-model', n_runs=1)
    report['generation'] = res
    return report


def restore_tuned(tuned: str):
    """Restart dspark on the tuned GGUF with default draft mode + persist env."""
    h = restart_dspark(target=tuned, draft_mode='none')
    with open(ENV_FILE, 'w') as f:
        f.write(f"DSPARK_TARGET={tuned}\n")
    log(f"tuned restored: {h.get('model') if h else 'UNHEALTHY'}")
    return h


# Top-level report keys owned by this script — everything else (e.g. a
# hand-added 'model_identity' annotation block) is carried forward across
# runs instead of being wiped by the wholesale rewrite.
_SCRIPT_REPORT_KEYS = {'timestamp', 'mode', 'steps'}


def write_report(report: dict):
    """Persist the benchmark report, preserving non-script annotation keys.

    The report is rebuilt from scratch each run and json.dump'd wholesale, which
    used to wipe any manually-added top-level keys (e.g. 'model_identity' with
    the deployed-GGUF sha256s) and nested annotations (corrected_mean /
    corrected_source in steps.before_deploy_historical). Load the previous
    report if present and carry forward any annotation this script does not own
    (fresh values always win), so annotations survive re-runs.
    """
    prev = {}
    if os.path.isfile(REPORT_JSON):
        try:
            with open(REPORT_JSON) as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                prev = parsed
        except Exception:
            prev = {}  # corrupt/absent previous report — start fresh
    for k, v in prev.items():
        if k not in _SCRIPT_REPORT_KEYS and k not in report:
            report[k] = v
    # Nested manual annotations in before_deploy_historical (e.g. corrected_mean
    # / corrected_source) live inside the script-owned 'steps' dict and would be
    # rebuilt fresh each run — carry them forward too when absent. Guard the
    # nested shapes the same way as the top level: a hand-corrupted previous
    # report (steps or before_deploy_historical as a non-dict) must never crash
    # the final write and lose the freshly-benchmarked report.
    prev_steps = prev.get('steps') if isinstance(prev.get('steps'), dict) else {}
    prev_bdh = prev_steps.get('before_deploy_historical')
    if not isinstance(prev_bdh, dict):
        prev_bdh = {}
    fresh_bdh = report.setdefault('steps', {}).setdefault('before_deploy_historical', {})
    for nk in ('corrected_mean', 'corrected_source'):
        if nk in prev_bdh and nk not in fresh_bdh:
            fresh_bdh[nk] = prev_bdh[nk]
    with open(REPORT_JSON, 'w') as f:
        json.dump(report, f, indent=2)


def main():
    ap = argparse.ArgumentParser(description='dspark throughput + draft-mode benchmark')
    ap.add_argument('--wait', dest='wait', action='store_true',
                    help='Wait for the tuned-GGUF deploy, then benchmark (default)')
    ap.add_argument('--now', dest='wait', action='store_false',
                    help='Benchmark whatever dspark is currently serving')
    ap.add_argument('--no-stock-control', action='store_true',
                    help='Skip the post-deploy stock swap benchmark')
    args = ap.parse_args()

    os.makedirs(DATA, exist_ok=True)

    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mode': 'wait' if args.wait else 'now',
        'steps': {},
    }

    # Historical stock baseline (before-deploy).
    report['steps']['before_deploy_historical'] = historical_baseline()
    log(f"historical stock baseline (pre-training dspark.log): "
        f"{report['steps']['before_deploy_historical']['mean']} tok/s mean "
        f"{report['steps']['before_deploy_historical']['last_measured']}")

    if args.wait:
        log("--- waiting for tuned-GGUF deploy ---")
        tuned = ''
        deadline = time.time() + 7200
        while time.time() < deadline:
            tuned = read_tuned_target()
            h = get_health()
            if tuned and h and h.get('status') == 'ok' and \
                    dspark_serves(os.path.basename(tuned)):
                break
            time.sleep(20)
        # Fail unless the served model actually IS the tuned GGUF — a healthy
        # dspark serving stock (stale env) must NOT be benchmarked as "tuned".
        h = get_health()
        if (not tuned or not h or h.get('status') != 'ok'
                or not dspark_serves(os.path.basename(tuned))):
            log(f"FAIL: deploy did not complete within 7200s. tuned={tuned!r} "
                f"served={h.get('model') if h else None}")
            write_report(report)
            sys.exit(1)
        log(f"tuned model deployed & healthy: {h.get('model')} "
            f"(draft_mode={h.get('draft_mode')})")

        # Let the A/B test harness run first — it generates through the same dspark.
        wait_ab_test_done()
        # Fresh health after A/B (its generations feed the rolling stats window).
        h = get_health() or {}
    else:
        tuned = read_tuned_target()
        if not tuned or not os.path.isfile(tuned):
            log("FAIL: --now requires a tuned GGUF in scripts/dspark-target.env "
                "(deploy first). Refusing to benchmark stock as 'tuned'.")
            sys.exit(1)
        h = get_health() or {}
        if h.get('status') != 'ok':
            log("FAIL: dspark not healthy for --now mode")
            sys.exit(1)
        log(f"dspark currently serving: {h.get('model')} "
            f"(draft_mode={h.get('draft_mode')})")

    report['steps']['deployed_health'] = h

    # After-deploy: benchmark the tuned model.
    log(f"--- benchmarking tuned model ({h.get('model')}) ---")
    report['steps']['tuned_benchmark'] = benchmark('tuned', NUM_RUNS)
    log(f"tuned client tps mean: {report['steps']['tuned_benchmark']['client_tps_mean']} "
        f"(server rolling stats incl. A/B traffic: "
        f"{report['steps']['tuned_benchmark']['health_stats']})")

    # Draft-mode verification with the tuned GGUF.
    report['steps']['draft_mode'] = verify_draft_mode(tuned)
    if report['steps']['draft_mode'].get('ok'):
        log("DRAFT-MODE OK: speculative decoding works with the tuned GGUF")
    else:
        log("DRAFT-MODE FAIL: see report")

    # Restore tuned + default mode BEFORE the stock control so the app keeps
    # serving the tuned model if the stock step crashes.
    report['steps']['restore_after_draft'] = restore_tuned(tuned)

    # Stock control benchmark (fresh same-hardware "before" data). Wrapped in
    # try/finally so a crash mid-swap can NEVER leave dspark serving stock.
    try:
        if not args.no_stock_control and os.path.isfile(STOCK_GGUF):
            log("--- stock control benchmark (same hardware) ---")
            h_stock = restart_dspark(target=STOCK_GGUF, draft_mode='none')
            if h_stock:
                report['steps']['stock_benchmark'] = benchmark('stock', NUM_RUNS)
                log(f"stock client tps mean: "
                    f"{report['steps']['stock_benchmark']['client_tps_mean']} "
                    f"(server stats: {report['steps']['stock_benchmark']['health_stats']})")
            else:
                report['steps']['stock_benchmark'] = {'error': 'dspark unhealthy on stock'}
                log("FAIL: dspark unhealthy on stock GGUF")
        else:
            log("stock control skipped (--no-stock-control or stock GGUF missing)")
    except Exception as e:
        report['steps']['stock_benchmark'] = {'error': str(e)}
        log(f"stock control raised: {e}")
    finally:
        log("--- restoring tuned model (final) ---")
        report['steps']['final_health'] = restore_tuned(tuned)

    # Summary table.
    log('--- summary ---')
    for key in ('before_deploy_historical', 'tuned_benchmark', 'stock_benchmark'):
        step = report['steps'].get(key, {})
        if isinstance(step, dict) and 'client_tps_mean' in step:
            log(f"  {key}: {step['client_tps_mean']} tok/s (client mean)")

    write_report(report)
    log(f"report written: {REPORT_JSON}")
    log("DONE")


if __name__ == '__main__':
    main()
