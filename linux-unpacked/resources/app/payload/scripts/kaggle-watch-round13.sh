#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog for the round-13 Kaggle kernel (vaca-qlora-round13)
# =============================================================================
# Polls the kernel every 5 minutes and ALERTS when the status leaves RUNNING:
#   - COMPLETE  → downloads the trained artifacts (adapter + merged safetensors)
#                 via the Range-resume downloader (scripts/download-round13-merged.py)
#                 then converts -> q4_k_m GGUF, deploys to dspark :8000, and
#                 drops the old R12 model copy (scripts/deploy-round13.sh — R12
#                 backup-guarded)
#   - ERROR     → alerts loudly and attempts artifact recovery anyway
#
# Usage:
#   bash scripts/kaggle-watch-round13.sh                 # long-running watchdog
#   bash scripts/kaggle-watch-round13.sh --once          # single status check
#   bash scripts/kaggle-watch-round13.sh --no-deploy     # download only
#   KAGGLE_WATCH_POLL=300 bash scripts/kaggle-watch-round13.sh
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
KERNEL="stevenawoods/vaca-qlora-round13"
OUT_DIR="$PROJECT_ROOT/training/cloud/out/round13"
LOG="${KAGGLE_WATCH_LOG:-/tmp/kaggle-watch-round13.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
MAX_LOOPS=150

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
PREV=""

i=0
while [ $i -lt $MAX_LOOPS ]; do
  i=$((i+1))
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo 'UNKNOWN')"
  TS="$(date '+%Y-%m-%d %H:%M:%S')"

  if [ -n "$PREV" ] && [ "$STATUS" != "$PREV" ]; then
    echo "[watch-r13] $TS 🚨 ALERT — status changed: $PREV → $STATUS" | tee -a "$LOG"
  fi
  echo "[watch-r13] $TS poll #$i — $KERNEL: $STATUS" | tee -a "$LOG"
  PREV="$STATUS"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      echo "[watch-r13] $TS ✅ ALERT — kernel COMPLETE. Downloading artifacts..." | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round13-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-13 artifacts downloaded'; then
        echo "[watch-r13] $TS ✅ Download OK at $OUT_DIR" | tee -a "$LOG"
        if [ "$NO_DEPLOY" = "1" ]; then
          echo "[watch-r13] --no-deploy set — skipping deploy." | tee -a "$LOG"
          exit 0
        fi
        echo "[watch-r13] $TS 🔄 Deploying round-13 model (convert → q4_k_m → dspark → drop R12)..."
        echo "[watch-r13] $TS 🔄 Deploying round-13 model (convert → q4_k_m → dspark → drop R12)..." | tee -a "$LOG"
        if bash "$SCRIPT_DIR/deploy-round13.sh" 2>&1 | tee -a "$LOG" | grep -q '✅ Round-13 model deployed'; then
          echo "[watch-r13] $TS ✅ Round-13 model DEPLOYED. Old R12 dropped (backup preserved)." | tee -a "$LOG"
          exit 0
        fi
        echo "[watch-r13] $TS ⚠️  deploy-round13.sh did not finish cleanly — inspect above." | tee -a "$LOG"
        exit 4
      fi
      echo "[watch-r13] $TS ⚠️  download incomplete — rerun download-round13-merged.py (range-resume safe)." | tee -a "$LOG"
      exit 1
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      echo "[watch-r13] $TS 🚨 ALERT — kernel $STATUS. Attempting artifact recovery..." | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round13-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-13 artifacts downloaded'; then
        echo "[watch-r13] $TS ✅ Artifacts recovered despite $STATUS" | tee -a "$LOG"
        [ "$NO_DEPLOY" = "1" ] && exit 0
        bash "$SCRIPT_DIR/deploy-round13.sh" 2>&1 | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-r13] $TS ❌ Kernel $STATUS and no recoverable output — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
  esac
done

echo "[watch-r13] timed out after $((MAX_LOOPS * POLL / 60)) minutes" | tee -a "$LOG"
exit 3
