#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog: poll the Kaggle round-6 kernel and prep the adapter for the
# Lightning AI handoff the moment it COMPLETES.
#
# Usage:
#   bash scripts/kaggle-watch-round6.sh            # long-running watch
#   bash scripts/kaggle-watch-round6.sh --once     # single status check
#
# On completion: runs `bash download_round6.sh` (writes out/round6-adapter/)
# and logs the outcome to data/watch-round6.log. Log back in / re-run this
# script after a crash to resume watching (state is idempotent: if the
# adapter already exists it just reports and exits 0).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

KERNEL="stevenawoods/vaca-qlora-round6"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADAPTER_DIR="$ROOT/training/cloud/out/round6-adapter"
LOG="$ROOT/data/watch-round6.log"
DOWNLOAD_SH="$ROOT/training/cloud/download_round6.sh"

# Idempotency: if the round-6 adapter is already in place, nothing to do.
if [ -f "$ADAPTER_DIR/adapter_config.json" ]; then
  echo "[watch-round6] adapter already present at $ADAPTER_DIR — nothing to do" | tee -a "$LOG"
  exit 0
fi

if [ ! -f "$DOWNLOAD_SH" ]; then
  # fallback: the script lives in the Desktop bundle folder too
  DOWNLOAD_SH="$HOME/Desktop/new training data set/download_round6.sh"
fi

POLL=600   # seconds between polls (10 min)
MAX_LOOPS=$(( 60 * 24 ))  # 24h cap

i=0
while [ $i -lt $MAX_LOOPS ]; do
  i=$((i+1))
  STATUS="$(kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo 'UNKNOWN')"
  TS="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[watch-round6] $TS poll #$i — $KERNEL: $STATUS" | tee -a "$LOG"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      echo "[watch-round6] $TS ✅ Kernel complete — downloading adapter..." | tee -a "$LOG"
      bash "$DOWNLOAD_SH" >> "$LOG" 2>&1 || { echo "[watch-round6] download_round6.sh failed" | tee -a "$LOG"; exit 1; }
      echo "[watch-round6] $TS ✅ Adapter ready at $ADAPTER_DIR" | tee -a "$LOG"
      exit 0
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      # The round-6 kernel crashes AFTER training in the GGUF-export cell
      # (nbformat metadata error), but the adapter (checkpoint-662/) is already
      # in /kaggle/working/out — so ALWAYS attempt the download: the output zip
      # is available for errored kernels too, and losing the adapter would
      # forfeit a finished 13-hour run.
      echo "[watch-round6] $TS ⚠️ Kernel $STATUS — attempting adapter download anyway (output exists)" | tee -a "$LOG"
      if bash "$DOWNLOAD_SH" >> "$LOG" 2>&1; then
        echo "[watch-round6] $TS ✅ Adapter ready at $ADAPTER_DIR despite kernel $STATUS" | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-round6] $TS ❌ Kernel $STATUS and download failed — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
  esac
done

echo "[watch-round6] timed out after 24h" | tee -a "$LOG"
exit 3
