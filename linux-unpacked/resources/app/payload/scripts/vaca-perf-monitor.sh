#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# vaca-perf-monitor.sh — PERFORMANCE monitor for the VACA build pipeline.
#
# There are already two monitors; neither measures latency:
#   scripts/vaca-stability-monitor.sh  → is anything crash-looping? (restart counts)
#   scripts/monitor-vaca.py            → is a reply CORRECT? (canned/empty/declined)
#
# This one answers "where does the time go, and is the GPU actually busy?".
#
# PASSIVE (default) — every INTERVAL seconds, append one line:
#   gpu/vram per GPU        → reveals GPU starvation during a build
#   backend health + llm.up → reveals degradation without a restart
#   new backend error lines → reveals the tsc compile-check repair loop
#   chat turns              → real user traffic throughput
#   process PIDs            → reveals silent restarts
#
# ACTIVE (--probe SECS) — additionally drive a real build every SECS and log
#   wall time + failure counts, giving a latency series over time. A probe costs
#   real GPU time and is visible in the app, so it is OFF by default.
#
# Log:   scripts/perf-monitor.log   (append-only, `key=value` — greppable)
# Usage: bash scripts/vaca-perf-monitor.sh                # passive, until stopped
#        bash scripts/vaca-perf-monitor.sh 60             # passive, every 60s
#        bash scripts/vaca-perf-monitor.sh --probe 900    # + build probe every 15m
#        bash scripts/vaca-perf-monitor.sh --stop
#        bash scripts/vaca-perf-monitor.sh --report       # summarise the log
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/scripts/perf-monitor.log"
PID_FILE="$ROOT/scripts/perf-monitor.pid"
BACKEND_LOG="$ROOT/scripts/backend.log"
CHAT_LOG="$ROOT/data/monitor/conversations.jsonl"

INTERVAL=30
PROBE_EVERY=0
BACKEND=http://127.0.0.1:3001
DSPARK=http://127.0.0.1:8000

say() { printf '\033[1;34m[perf-monitor]\033[0m %s\n' "$*"; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" 2>/dev/null || echo 000; }

# ─── report mode: summarise what has been collected ────────────────────────
if [ "${1:-}" = "--report" ]; then
  python3 - "$LOG" <<'PY'
import sys, re, statistics as st
path=sys.argv[1]
try: lines=[l.strip() for l in open(path) if l.strip() and not l.startswith('#')]
except FileNotFoundError: print('no log yet'); raise SystemExit
if not lines: print('log empty'); raise SystemExit
def nums(key):
    out=[]
    for l in lines:
        m=re.search(rf'{key}=([0-9.]+)', l)
        if m: out.append(float(m.group(1)))
    return out
def gpu_utils(l):
    m=re.search(r'gpu=([0-9/,]+)', l)
    return [int(x) for x in m.group(1).split('/') if x!=''] if m else []
allu=[u for l in lines for u in gpu_utils(l)]
print(f'samples: {len(lines)}')
if allu:
    print(f'GPU util  mean {sum(allu)/len(allu):5.1f}%   median {sorted(allu)[len(allu)//2]:3d}%   max {max(allu)}%')
    print(f'          idle(0%) {100*sum(1 for u in allu if u==0)/len(allu):4.0f}% of samples    busy(>50%) {100*sum(1 for u in allu if u>50)/len(allu):4.0f}%')
pt=nums('probe_total_ms')
if pt:
    print(f'build wall time  n={len(pt)}  median {st.median(pt)/1000:6.1f}s   min {min(pt)/1000:6.1f}s   max {max(pt)/1000:6.1f}s')
pf=nums('probe_failed')
if pf:
    bad=sum(1 for x in pf if x>0)
    print(f'builds with failing files: {bad}/{len(pf)} ({100*bad/len(pf):.0f}%)')
cr=nums('compile_rounds')
if cr: print(f'compile-check repair rounds observed: {int(sum(cr))}')
PY
  exit 0
fi

# ─── stop mode ─────────────────────────────────────────────────────────────
if [ "${1:-}" = "--stop" ]; then
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" && say "stopped (pid $(cat "$PID_FILE"))"; rm -f "$PID_FILE"
  else
    say "not running"
  fi
  exit 0
fi

# ─── args ──────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--probe" ]; then
  PROBE_EVERY="${2:-900}"
elif [ -n "${1:-}" ] && [[ "${1}" =~ ^[0-9]+$ ]]; then
  INTERVAL="$1"
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  say "already running (pid $(cat "$PID_FILE")) — log: $LOG"; exit 0
fi

echo $$ > "$PID_FILE"
echo "# perf-monitor started $(date '+%F %T') interval=${INTERVAL}s probe=${PROBE_EVERY:-off}" >> "$LOG"
say "started (pid $$) every ${INTERVAL}s → $LOG"

prev_err=0
prev_chat=0
prev_compile=0
[ -f "$BACKEND_LOG" ] && prev_err=$(wc -l < "$BACKEND_LOG")
[ -f "$CHAT_LOG" ]    && prev_chat=$(wc -l < "$CHAT_LOG")

trap 'echo "# perf-monitor stopped $(date "+%F %T")" >> "$LOG"; rm -f "$PID_FILE"; exit 0' TERM INT
# Wait a FULL probe interval before the first build probe.  Starting one
# immediately means it queues behind whatever build the user just kicked off
# (the endpoint is single-flight), which measures nothing and adds load.
last_probe=$(date +%s)
while true; do
  now=$(date +%s)
  gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | tr '\n' '/')
  vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | tr '\n' '/')
  bcode=$(code "$BACKEND/api/health")
  llm=$(curl -s --max-time 5 "$BACKEND/api/health" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("llm",{}).get("up"))' 2>/dev/null || echo '?')
  dcode=$(code "$DSPARK/v1/health")

  errs=0; compile=0; blog=0
  if [ -f "$BACKEND_LOG" ]; then
    cur=$(wc -l < "$BACKEND_LOG")
    if [ "$cur" -gt "$prev_err" ]; then
      blog=$((cur - prev_err))
      new=$(tail -n $((cur - prev_err)) "$BACKEND_LOG")
      errs=$(printf '%s\n' "$new" | grep -ciE 'error|failed|timeout|econn' || true)
      compile=$(printf '%s\n' "$new" | grep -c 'Compile-check round' || true)
    fi
    prev_err=$cur
  fi
  chat=0
  [ -f "$CHAT_LOG" ] && chat=$(wc -l < "$CHAT_LOG")
  newchat=$((chat - prev_chat)); prev_chat=$chat

  # blog=+N is backend-log growth: a cheap, reliable "something is building"
  # signal, so GPU util can be read against real activity.
  line="$(date '+%F %T') gpu=${gpu} vram=${vram} backend=${bcode} llm=${llm} dspark=${dcode} chat=+${newchat} blog=+${blog} errs=+${errs} compile_rounds=+${compile}"
  echo "$line" >> "$LOG"

  # ── optional active probe, ASYNC ───────────────────────────────────────
  # Runs in the background and appends its own log line when it finishes, so
  # the sample loop above keeps recording DURING a build — which is exactly
  # when the interesting data is.  Skipped if a build is already in flight:
  # the endpoint is single-flight, so a probe would just queue behind the
  # user's build and then run a second heavy build for no reason.
  if [ "${PROBE_EVERY:-0}" -gt 0 ] && [ $((now - last_probe)) -ge "$PROBE_EVERY" ]; then
    if pgrep -f '[b]lueprint/build' >/dev/null 2>&1; then
      echo "$(date '+%F %T') probe=skipped-already-building" >> "$LOG"
      last_probe=$now
    else
      last_probe=$now
      (
        t0=$(date +%s%N)
        body=$(curl -s --max-time 900 -X POST "$BACKEND/api/blueprint/build" \
          -H 'Content-Type: application/json' \
          -d '{"goal":"Create a single-file HTML task manager with add, complete and delete, plus localStorage persistence"}')
        t1=$(date +%s%N)
        ms=$(( (t1 - t0) / 1000000 ))
        stats=$(printf '%s' "$body" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("failed=-1 errors=-1 tsc=?"); raise SystemExit
print("failed=%s errors=%s tsc=%s" % (d.get("failedCount",-1), d.get("totalErrors",-1), d.get("tsCompileClean")))
' 2>/dev/null || echo "failed=-1 errors=-1 tsc=?")
        echo "$(date '+%F %T') probe_done probe_total_ms=${ms} ${stats}" >> "$LOG"
      ) &
    fi
  fi

  sleep "$INTERVAL"
done
