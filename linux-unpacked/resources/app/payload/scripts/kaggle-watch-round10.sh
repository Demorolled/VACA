#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog for the round-10 Kaggle kernel (vaca-qlora-round10)
# =============================================================================
# Polls the kernel until it completes (or fails). On completion it:
#   1. downloads the trained artifacts (adapter + merged safetensors) via the
#      Range-resume downloader (scripts/download-round10-merged.py)
#   2. converts -> q4_k_m GGUF, deploys to dspark :8000, and drops the old R9
#      model copy (scripts/deploy-round10.sh)
#
# Usage:
#   bash scripts/kaggle-watch-round10.sh                # long-running watchdog
#   bash scripts/kaggle-watch-round10.sh --once         # single status check
#   bash scripts/kaggle-watch-round10.sh --no-deploy    # download only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-watch-round10.sh
#
# Exit codes: 0 = deployed · 1 = failed & download failed · 2 = creds
#             3 = still running (--once) · 4 = deployed but health-check failed
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ONCE=0
NO_DEPLOY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1 ;;
    --no-deploy) NO_DEPLOY=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --once | --no-deploy)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KERNEL="stevenawoods/vaca-qlora-round10"
OUT_DIR="$PROJECT_ROOT/training/cloud/out/round10"
LOG="/tmp/kaggle-watch-round10.log"
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
  echo "[watch-r10] $TS poll #$i — $KERNEL: $STATUS" | tee -a "$LOG"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      echo "[watch-r10] $TS ✅ Kernel complete — downloading artifacts..." | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round10-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-10 artifacts downloaded'; then
        echo "[watch-r10] $TS ✅ Download OK at $OUT_DIR" | tee -a "$LOG"
        if [ "$NO_DEPLOY" = "1" ]; then
          echo "[watch-r10] --no-deploy set — skipping deploy." | tee -a "$LOG"
          exit 0
        fi
        echo "[watch-r10] $TS 🔄 Deploying round-10 model (convert → q4_k_m → dspark → drop R9)..." | tee -a "$LOG"
        if bash "$SCRIPT_DIR/deploy-round10.sh" 2>&1 | tee -a "$LOG" | grep -q '✅ Round-10 model deployed'; then
          echo "[watch-r10] $TS ✅ Round-10 model DEPLOYED. Old R9 dropped." | tee -a "$LOG"
          echo "[watch-r10] $TS 🧹 Running gated cleanup of staged pre-round-10 data..." | tee -a "$LOG"
          if bash "$SCRIPT_DIR/cleanup-round10-pending.sh" 2>&1 | tee -a "$LOG" | tail -1 | grep -q 'deleted'; then
            echo "[watch-r10] $TS 🧹 Staged data deleted (gates passed)." | tee -a "$LOG"
          else
            echo "[watch-r10] $TS ⚠️  Cleanup skipped or gated — staged data kept (safe)." | tee -a "$LOG"
          fi
          exit 0
        fi
        echo "[watch-r10] $TS ⚠️  deploy-round10.sh did not finish cleanly — inspect above." | tee -a "$LOG"
        exit 4
      fi
      echo "[watch-r10] $TS ⚠️  download incomplete — rerun download-round10-merged.py (range-resume safe)." | tee -a "$LOG"
      exit 1
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      echo "[watch-r10] $TS ⚠️ Kernel $STATUS — attempting download anyway (trained artifacts may exist)" | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round10-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-10 artifacts downloaded'; then
        echo "[watch-r10] $TS ✅ Artifacts recovered despite $STATUS" | tee -a "$LOG"
        [ "$NO_DEPLOY" = "1" ] && exit 0
        bash "$SCRIPT_DIR/deploy-round10.sh" 2>&1 | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-r10] $TS ❌ Kernel $STATUS and no recoverable output — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
  esac
done

echo "[watch-r10] timed out after $((MAX_LOOPS * POLL / 60)) minutes" | tee -a "$LOG"
exit 3
