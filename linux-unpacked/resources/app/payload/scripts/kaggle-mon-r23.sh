#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-mon-r23.sh — REMOTE MONITOR for the Kaggle R23 training kernel
# =============================================================================
# Polls the Kaggle kernel status via the API and, once it completes, downloads
# the output (adapter + progress.json) and prints the final loss summary.
#
#   - Survives SSH/VNC disconnects: launch detached (setsid) and read the log.
#   - Live loss: open the kernel URL in a browser — Kaggle streams stdout live
#     (the trainer prints HEARTBEAT {step, max_steps, loss} every 5 steps).
#
# Usage:
#   bash scripts/kaggle-mon-r23.sh            # long-running watch (detached ok)
#   bash scripts/kaggle-mon-r23.sh --once     # single status check
#
# Log: data/watch-r23-kaggle.log
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

KERNEL="stevenawoods/vaca-r23-qlora-combined-rag-14b-t4-x2-notebook"
URL="https://www.kaggle.com/code/$KERNEL"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/training/cloud/kaggle-r23-output"
LOG="$ROOT/data/watch-r23-kaggle.log"
POLL=60            # seconds between polls
MAX_LOOPS=$(( 60 * 12 ))  # 12h cap

mkdir -p "$OUT_DIR" "$(dirname "$LOG")"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ─── helpers ────────────────────────────────────────────────────────────────
status_of() {
  kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo "UNKNOWN"
}

elapsed_of() {
  kaggle kernels list --mine 2>/dev/null | awk -v k="$KERNEL" '$1==k {print $4; exit}'
}

show_progress() {
  # If Kaggle already serves output (running kernels sometimes do, done always),
  # extract progress.json and show it.
  local tmp; tmp="$(mktemp -d)"
  if kaggle kernels output "$KERNEL" -p "$tmp" >/dev/null 2>&1; then
    local pf="$tmp/round23-kaggle/progress.json"
    if [ -f "$pf" ]; then
      say "📊 $(python3 -c "import json;d=json.load(open('$pf'));print({k:v for k,v in d.items() if k not in ('pid',)})")"
    fi
    # keep whatever came down (adapter may be partial)
    cp -rn "$tmp"/. "$OUT_DIR"/ 2>/dev/null || true
    say "  output snapshot → $OUT_DIR"
  fi
  rm -rf "$tmp"
}

# ─── idempotency: already downloaded? ───────────────────────────────────────
if [ -f "$OUT_DIR/round23-kaggle/final/adapter_config.json" ]; then
  say "✅ R23 adapter already downloaded at $OUT_DIR/round23-kaggle/final — nothing to do."
  exit 0
fi

say "👀 R23 Kaggle monitor started — kernel: $KERNEL"
say "   Live view (browser): $URL"

i=0
START="$(date +%s)"
while [ $i -lt $MAX_LOOPS ]; do
  i=$((i + 1))
  STATUS="$(status_of)"
  ELAPSED="$(( ($(date +%s) - START) / 60 ))m"
  say "poll #$i — status: $STATUS (monitor elapsed $ELAPSED)"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*QUEUED*|*UNKNOWN*)
      show_progress
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      say "✅ Kernel COMPLETE — downloading output…"
      show_progress
      # final pull (output only exists for real once complete)
      if kaggle kernels output "$KERNEL" -p "$OUT_DIR" 2>/dev/null; then
        say "   output → $OUT_DIR"
      fi
      PF="$OUT_DIR/round23-kaggle/progress.json"
      if [ -f "$PF" ]; then
        say "📊 FINAL: $(python3 -c "import json;print(json.load(open('$PF')))")"
      fi
      if [ -f "$OUT_DIR/round23-kaggle/final/adapter_config.json" ]; then
        say "🎉 ADAPTER READY → $OUT_DIR/round23-kaggle/final/"
        say "   Next: merge on the agent (scripts/build-r23-merged.py) + GGUF + deploy."
      fi
      exit 0
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      say "⚠️ Kernel $STATUS (may flip to RUNNING when a new run is committed) — snapshotting…"
      show_progress
      say "   Live view: $URL"
      [ "$ONCE" = "1" ] && exit 1
      sleep "$POLL"
      ;;
  esac
done

say "timed out after 12h — last status: $(status_of)"
exit 3
