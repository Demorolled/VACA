#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog for the GUI-combined Kaggle kernel (vaca-qlora-gui)
# =============================================================================
# Polls the kernel until it completes (or fails), then downloads the output
# (results.zip: adapter + tuned GGUF) into training/cloud/out/gui-round/.
#
# Usage:
#   bash scripts/kaggle-watch-gui.sh                # long-running watchdog
#   bash scripts/kaggle-watch-gui.sh --once         # single status check
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-watch-gui.sh
#
# Exit codes: 0 = output ready · 1 = failed & download failed · 2 = creds
#             3 = still running (--once)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ONCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --once)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KERNEL="${KAGGLE_KERNEL:-stevenawoods/vaca-qlora-gui}"
OUT_DIR="$PROJECT_ROOT/training/cloud/out/gui-round"
LOG="/tmp/kaggle-watch-gui.log"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
MAX_LOOPS=240                       # ~20 h cap (Kaggle's own limit is 12 h)

# ─── Credentials ────────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or access_token)." >&2
  exit 2
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 2
fi
KERNEL="${USERNAME}/${KERNEL#*/}"

mkdir -p "$OUT_DIR"

i=0
while [ $i -lt $MAX_LOOPS ]; do
  i=$((i+1))
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo 'UNKNOWN')"
  TS="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[watch-gui] $TS poll #$i — $KERNEL: $STATUS" | tee -a "$LOG"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      echo "[watch-gui] $TS ✅ Kernel complete — downloading output..." | tee -a "$LOG"
      if timeout 3600 kaggle kernels output "$KERNEL" -p "$OUT_DIR" >/dev/null 2>&1; then
        echo "[watch-gui] $TS ✅ Output ready at $OUT_DIR" | tee -a "$LOG"
        ls -lh "$OUT_DIR" | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-gui] $TS ⚠️  complete but download failed — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      echo "[watch-gui] $TS ⚠️ Kernel $STATUS — attempting download anyway (output may exist)" | tee -a "$LOG"
      if timeout 3600 kaggle kernels output "$KERNEL" -p "$OUT_DIR" >/dev/null 2>&1; then
        echo "[watch-gui] $TS ✅ Output recovered despite $STATUS" | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-gui] $TS ❌ Kernel $STATUS and no output — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
  esac
done

echo "[watch-gui] timed out after $((MAX_LOOPS * POLL / 60)) minutes" | tee -a "$LOG"
exit 3
