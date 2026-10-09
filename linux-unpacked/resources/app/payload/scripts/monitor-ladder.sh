#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build-Ladder monitor: one-shot status snapshot + optional --watch loop.
# =============================================================================
#   bash scripts/monitor-ladder.sh                 # single snapshot
#   bash scripts/monitor-ladder.sh --watch 60      # loop every 60s
#   bash scripts/monitor-ladder.sh --json          # machine-readable snapshot
#
# Reports:
#   - ladder progress (N/40 builds, pass/fail, current goal if a run is live)
#   - dspark + backend health
#   - training dataset size (verified-generations rows added by the ladder)
#   - Kaggle dataset status (vaca-ladder-r1)
#   - open repair/fix-list status from the improvement report
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$ROOT/data/build-ladder-results.jsonl"
VERIFIED="$ROOT/training/dataset/verified-generations.jsonl"
REPORT="$ROOT/data/build-improvement-report.md"
KAGGLE_SLUG="stevenawoods/vaca-ladder-r1"

WATCH=0
JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --watch) WATCH=1; INTERVAL="${2:-60}"; shift 2 ;;
    --json) JSON=1; shift ;;
    *) echo "❌ Unknown arg: $1 (--watch N | --json)" >&2; exit 1 ;;
  esac
done

snapshot() {
  local ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # ── Ladder progress (unique build numbers with their last run) ──
  local done_count=0 pass_count=0 fail_count=0 median_err=0 median_dur=0 captured=0
  if [ -f "$RESULTS" ]; then
    local stats
    stats="$(python3 - "$RESULTS" <<'EOF'
import json, sys, statistics
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
by = {}
for r in rows:
    by[r['number']] = r
last = [by[n] for n in sorted(by)]
passes = sum(1 for r in last if r.get('isAllValidated'))
errs = [r.get('totalErrors') or 0 for r in last]
durs = [r['durationMs']/1000 for r in last]
captured = sum((r.get('verifiedCapture') or {}).get('captured', 0) for r in last)
print(f"{len(last)}|{passes}|{len(last)-passes}|{statistics.median(errs) if errs else 0}|{statistics.median(durs) if durs else 0:.0f}|{captured}")
EOF
)"
    done_count="${stats%%|*}"; rest="${stats#*|}"
    pass_count="${rest%%|*}"; rest="${rest#*|}"
    fail_count="${rest%%|*}"; rest="${rest#*|}"
    median_err="${rest%%|*}"; rest="${rest#*|}"
    median_dur="${rest%%|*}"; rest="${rest#*|}"
    captured="${rest%%|*}"
  fi

  # ── Verified dataset growth ──
  local verified_rows=0
  [ -f "$VERIFIED" ] && verified_rows="$(wc -l < "$VERIFIED")"

  # ── Server health ──
  local api="down" dspark="down" model="?"
  if curl -s --max-time 4 http://localhost:3001/api/health >/dev/null 2>&1; then api="up"; fi
  local dh
  dh="$(curl -s --max-time 4 http://localhost:8000/v1/health 2>/dev/null || true)"
  if [ -n "$dh" ]; then
    dspark="up"
    model="$(echo "$dh" | python3 -c "import sys,json;print(json.load(sys.stdin).get('model','?'))" 2>/dev/null || echo '?')"
  fi

  # ── Kaggle dataset ──
  local kaggle="unknown"
  if timeout 30 kaggle datasets status "$KAGGLE_SLUG" >/dev/null 2>&1; then kaggle="ready"; fi

  # ── Improvement report fix-list status ──
  local fixes_open fixes_done
  fixes_open="$(grep -c '^- \[ \]' "$REPORT" 2>/dev/null || true)"
  fixes_done="$(grep -c '^- \[x\]' "$REPORT" 2>/dev/null || true)"
  fixes_open="${fixes_open:-0}"; fixes_done="${fixes_done:-0}"
  fixes_open="$(echo "$fixes_open" | tail -1)"
  fixes_done="$(echo "$fixes_done" | tail -1)"

  if [ "$JSON" = "1" ]; then
    python3 -c "
import json,sys
print(json.dumps({
  'timestamp': '$ts',
  'ladder': {'completed': $done_count, 'pass': $pass_count, 'fail': $fail_count,
             'medianErrorsPerBuild': $median_err, 'medianDurationS': $median_dur,
             'verifiedCaptured': $captured, 'total': 40},
  'dataset': {'verifiedRows': $verified_rows},
  'servers': {'api': '$api', 'dspark': '$dspark', 'model': '$model'},
  'kaggle': {'dataset': '$KAGGLE_SLUG', 'status': '$kaggle'},
  'improvementReport': {'fixesOpen': $fixes_open, 'fixesDone': $fixes_done},
}, indent=1))"
  else
  echo "── Build Ladder Monitor — $ts ──────────────────────"
  echo "  Ladder:      $done_count/40 builds | PASS $pass_count | FAIL $fail_count"
  echo "  Median:      $median_err errors/build | ${median_dur}s duration | $captured files captured"
    echo "  Dataset:     $verified_rows verified rows in verified-generations.jsonl"
    echo "  Servers:     api=$api | dspark=$dspark ($model)"
    echo "  Kaggle:      $KAGGLE_SLUG → $kaggle"
    echo "  Report:      $fixes_done/$((fixes_open + fixes_done)) fixes done"
  fi
}

if [ "$WATCH" = "1" ]; then
  while true; do snapshot; sleep "$INTERVAL"; done
else
  snapshot
fi
