#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog for the round-11 Kaggle kernel (vaca-qlora-round11)
# =============================================================================
# Polls the kernel every 5 minutes and ALERTS when the status leaves RUNNING:
#   - COMPLETE  → downloads the trained artifacts (adapter + merged safetensors)
#                 via the Range-resume downloader (scripts/download-round11-merged.py)
#                 then converts -> q4_k_m GGUF, deploys to dspark :8000, and
#                 drops the old R10 model copy (scripts/deploy-round11.sh — R10
#                 backup-guarded)
#   - ERROR     → alerts loudly and attempts artifact recovery anyway
#
# Every poll is logged (with ALERT markers on state changes) so you can see the
# whole history in one file. Default poll interval 5 min; override with
# KAGGLE_WATCH_POLL=<seconds>.
#
# Usage:
#   bash scripts/kaggle-watch-round11.sh                 # long-running watchdog
#   bash scripts/kaggle-watch-round11.sh --once          # single status check
#   bash scripts/kaggle-watch-round11.sh --no-deploy     # download only
#   KAGGLE_WATCH_POLL=300 bash scripts/kaggle-watch-round11.sh
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
KERNEL="stevenawoods/vaca-qlora-round11"
OUT_DIR="$PROJECT_ROOT/training/cloud/out/round11"
LOG="${KAGGLE_WATCH_LOG:-/tmp/kaggle-watch-round11.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
MAX_LOOPS=150                       # ~12.5 h cap (Kaggle's own limit is 12 h)

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
    echo "[watch-r11] $TS 🚨 ALERT — status changed: $PREV → $STATUS" | tee -a "$LOG"
  fi
  echo "[watch-r11] $TS poll #$i — $KERNEL: $STATUS" | tee -a "$LOG"
  PREV="$STATUS"

  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      echo "[watch-r11] $TS ✅ ALERT — kernel COMPLETE. Downloading artifacts..." | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round11-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-11 artifacts downloaded'; then
        echo "[watch-r11] $TS ✅ Download OK at $OUT_DIR" | tee -a "$LOG"
        if [ "$NO_DEPLOY" = "1" ]; then
          echo "[watch-r11] --no-deploy set — skipping deploy." | tee -a "$LOG"
          exit 0
        fi
        echo "[watch-r11] $TS 🔄 Deploying round-11 model (convert → q4_k_m → dspark → drop R10)..."
        echo "[watch-r11] $TS 🔄 Deploying round-11 model (convert → q4_k_m → dspark → drop R10)..." | tee -a "$LOG"
        if bash "$SCRIPT_DIR/deploy-round11.sh" 2>&1 | tee -a "$LOG" | grep -q '✅ Round-11 model deployed'; then
          echo "[watch-r11] $TS ✅ Round-11 model DEPLOYED. Old R10 dropped (backup preserved)." | tee -a "$LOG"
          exit 0
        fi
        echo "[watch-r11] $TS ⚠️  deploy-round11.sh did not finish cleanly — inspect above." | tee -a "$LOG"
        exit 4
      fi
      echo "[watch-r11] $TS ⚠️  download incomplete — rerun download-round11-merged.py (range-resume safe)." | tee -a "$LOG"
      exit 1
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      echo "[watch-r11] $TS 🚨 ALERT — kernel $STATUS. Attempting artifact recovery..." | tee -a "$LOG"
      if python3 "$SCRIPT_DIR/download-round11-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-11 artifacts downloaded'; then
        echo "[watch-r11] $TS ✅ Artifacts recovered despite $STATUS" | tee -a "$LOG"
        [ "$NO_DEPLOY" = "1" ] && exit 0
        bash "$SCRIPT_DIR/deploy-round11.sh" 2>&1 | tee -a "$LOG"
        exit 0
      fi
      echo "[watch-r11] $TS ❌ Kernel $STATUS and no recoverable output — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
  esac
done

echo "[watch-r11] timed out after $((MAX_LOOPS * POLL / 60)) minutes" | tee -a "$LOG"
exit 3
