#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-mon-sky1.sh — REMOTE MONITOR for the Kaggle Sky-T1 training kernel
# =============================================================================
# Polls the Kaggle kernel status via the API and, once it completes, downloads
# the output (the trained LoRA adapter for VACA Sky1) and prints the final
# loss summary — so the merge + Q4 step can run on the agent computer.
#
#   - Survives SSH/VNC disconnects: launch detached (setsid) and read the log.
#   - Live loss: open the kernel URL in a browser — Kaggle streams stdout live.
#
# Usage:
#   bash scripts/kaggle-mon-sky1.sh            # long-running watch (detached ok)
#   bash scripts/kaggle-mon-sky1.sh --once     # single status + snapshot check
#
# Log: data/watch-sky1-kaggle.log
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

KERNEL="stevenawoods/vaca-qlora-round-sky1"
URL="https://www.kaggle.com/code/$KERNEL"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/training/cloud/kaggle-sky1-output"
LOG="$ROOT/data/watch-sky1-kaggle.log"
POLL=60
MAX_LOOPS=$(( 60 * 48 ))   # 48h cap (full-corpus SFT is ~30-40h on dual T4)

mkdir -p "$OUT_DIR" "$(dirname "$LOG")"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

status_of() {
  python3 -m kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo "UNKNOWN"
}

show_progress() {
  local tmp; tmp="$(mktemp -d)"
  if python3 -m kaggle kernels output "$KERNEL" -p "$tmp" >/dev/null 2>&1; then
    local pf="$tmp/sky1-kaggle/progress.json"
    if [ -f "$pf" ]; then
      say "📊 $(python3 -c "import json;d=json.load(open('$pf'));print({k:v for k,v in d.items() if k not in ('pid',)})")"
    fi
    cp -rn "$tmp"/. "$OUT_DIR"/ 2>/dev/null || true
    [ -n "$(ls -A "$tmp" 2>/dev/null)" ] && say "  output snapshot → $OUT_DIR"
  fi
  rm -rf "$tmp"
}

# ─── idempotency: already downloaded? ───────────────────────────────────────
if [ -f "$OUT_DIR/sky1-kaggle/final/adapter_config.json" ]; then
  say "✅ Sky1 adapter already downloaded at $OUT_DIR/sky1-kaggle/final — nothing to do."
  exit 0
fi

say "👀 Sky1 Kaggle monitor started — kernel: $KERNEL"
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
      if python3 -m kaggle kernels output "$KERNEL" -p "$OUT_DIR" 2>/dev/null; then
        say "   output → $OUT_DIR"
      fi
      PF="$OUT_DIR/sky1-kaggle/progress.json"
      if [ -f "$PF" ]; then
        say "📊 FINAL: $(python3 -c "import json;print(json.load(open('$PF')))")"
      fi
      if [ -f "$OUT_DIR/sky1-kaggle/final/adapter_config.json" ]; then
        say "🎉 ADAPTER READY → $OUT_DIR/sky1-kaggle/final/"
        say "   Next: on the agent, merge + Q4 → scripts/build-sky1-merged.py"
      fi
      exit 0
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      say "⚠️ Kernel $STATUS (may flip to RUNNING when a new run is committed) — snapshotting…"
      show_progress
      [ "$ONCE" = "1" ] && exit 1
      sleep "$POLL"
      ;;
  esac
done

say "timed out after 48h — last status: $(status_of)"
exit 3