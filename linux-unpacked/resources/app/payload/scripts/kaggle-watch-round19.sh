#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Round-19 watchdog: polls the R19 Kaggle kernel (vaca-qlora-round19).
# =============================================================================
#   bash scripts/kaggle-watch-round19.sh               # long-running watchdog
#   bash scripts/kaggle-watch-round19.sh --once        # single status check
#   KAGGLE_WATCH_POLL=300 bash scripts/kaggle-watch-round19.sh
#
# On COMPLETE it downloads the trained adapter + merged safetensors into
# training/cloud/out/round19/ and prints the merge/deploy instructions
# (deploy is left to you so dspark is never touched mid-conversation).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

KERNEL="stevenawoods/vaca-qlora-round19"
LOG="${KAGGLE_WATCH_LOG:-/tmp/kaggle-watch-round19.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$ROOT/training/cloud/out/round19"
EST_TOTAL_MIN=390   # ~6-6.5 h on 1× T4 (1 epoch, ~1,900 rows capped, effective batch 8)

ONCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1 ;;
    *) echo "❌ Unknown arg: $1 (--once)" >&2; exit 1 ;;
  esac
  shift || true
done

TS() { date -u +%Y-%m-%dT%H:%M:%SZ; }
LOCAL() { date "+%Y-%m-%d %H:%M %Z"; }

echo "[watch-r19] $(TS) started (poll ${POLL}s) | kernel: $KERNEL" | tee -a "$LOG"
START_EPOCH="$(date +%s)"

while true; do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo UNKNOWN)"
  NOW_EPOCH="$(date +%s)"
  RUN_MIN=$(( (NOW_EPOCH - START_EPOCH) / 60 ))
  REMAIN_MIN=$(( EST_TOTAL_MIN - RUN_MIN ))
  if [ "$REMAIN_MIN" -lt 0 ]; then REMAIN_MIN=0; fi
  ETA_LOCAL="$(date -d "@$(( NOW_EPOCH + REMAIN_MIN * 60 ))" "+%H:%M %Z" 2>/dev/null || echo "?")"
  echo "[watch-r19] $(LOCAL) status: $STATUS | elapsed ${RUN_MIN}m | est remaining ${REMAIN_MIN}m (~$ETA_LOCAL)" | tee -a "$LOG"

  case "$STATUS" in
    running|queued|""|KernelWorkerStatus.RUNNING|KernelWorkerStatus.QUEUED)
      ;;
    COMPLETE|KernelWorkerStatus.COMPLETE)
      echo "[watch-r19] $(TS) ✅ COMPLETE after ${RUN_MIN}m — downloading results..." | tee -a "$LOG"
      mkdir -p "$OUT_DIR"
      cd /tmp
      timeout 900 kaggle kernels output "$KERNEL" -p /tmp/r19-out 2>&1 | tail -3 | tee -a "$LOG"
      if ls /tmp/r19-out/results.zip >/dev/null 2>&1; then
        cp /tmp/r19-out/results.zip "$OUT_DIR/results.zip"
        (cd "$OUT_DIR" && unzip -o -q results.zip 2>/dev/null || true)
        echo "[watch-r19] $(TS) ✅ results downloaded to $OUT_DIR" | tee -a "$LOG"
        echo "[watch-r19] $(TS) NEXT: build the merged 16-bit model + quantize + deploy:" | tee -a "$LOG"
        echo "[watch-r19] $(TS)   python3 scripts/download-round19-merged.py   (adapter + witness)" | tee -a "$LOG"
        echo "[watch-r19] $(TS)   python3 scripts/build-r19-merged.py          (real fp16 merged)" | tee -a "$LOG"
        echo "[watch-r19] $(TS)   bash scripts/deploy-round19.sh               (Q8->Q4, restart dspark)" | tee -a "$LOG"
      else
        echo "[watch-r19] $(TS) ⚠️ results.zip not found in kernel output — check the Output tab manually." | tee -a "$LOG"
      fi
      rm -rf /tmp/r19-out
      exit 0
      ;;
    ERROR|KernelWorkerStatus.ERROR|KernelWorkerStatus.KERNEL_WORKER_ERROR)
      echo "[watch-r19] $(TS) ❌ KERNEL ERROR — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
    *)
      echo "[watch-r19] $(TS) unknown status: $STATUS — continuing to poll." | tee -a "$LOG"
      ;;
  esac

  [ "$ONCE" = "1" ] && exit 0
  sleep "$POLL"
done
