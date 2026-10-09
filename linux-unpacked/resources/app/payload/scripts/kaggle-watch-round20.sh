#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Round-20 watchdog: polls the R20 ORPO Kaggle kernel and auto-downloads the
# trained adapter on completion.
# =============================================================================
#   bash scripts/kaggle-watch-round20.sh               # long-running watchdog
#   bash scripts/kaggle-watch-round20.sh --once        # single status check
#   KAGGLE_WATCH_POLL=300 bash scripts/kaggle-watch-round20.sh
#
# NOTE the kernel slug: the R20 title "VACA QLoRA Round20 (ORPO)" resolved to
# vaca-qlora-round20-ORPO (title-slug suffix) — the metadata id written by
# kaggle-setup-round20.sh is vaca-qlora-round20, which is NOT the real slug.
#
# On COMPLETE it downloads results.zip into training/cloud/out/round20/ and
# prints the LOCAL merge steps (R20 is --skip-merge by design — the 16-bit
# merge happens on this machine, build-r19-merged.py pattern; never in-kernel,
# that was the R19 OOM spot). Deploy is left to you: dspark is never touched
# mid-conversation.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

KERNEL="stevenawoods/vaca-qlora-round20-orpo"
LOG="${KAGGLE_WATCH_LOG:-/tmp/kaggle-watch-round20.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$ROOT/training/cloud/out/round20"
EST_TOTAL_MIN=60   # quota-fit: 1 epoch ORPO (~12 steps ≈ 29 min) + load/save ≈ 45-60 min

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

echo "[watch-r20] $(TS) started (poll ${POLL}s) | kernel: $KERNEL" | tee -a "$LOG"
START_EPOCH="$(date +%s)"

while true; do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo UNKNOWN)"
  NOW_EPOCH="$(date +%s)"
  RUN_MIN=$(( (NOW_EPOCH - START_EPOCH) / 60 ))
  REMAIN_MIN=$(( EST_TOTAL_MIN - RUN_MIN ))
  if [ "$REMAIN_MIN" -lt 0 ]; then REMAIN_MIN=0; fi
  ETA_LOCAL="$(date -d "@$(( NOW_EPOCH + REMAIN_MIN * 60 ))" "+%H:%M %Z" 2>/dev/null || echo "?")"
  echo "[watch-r20] $(LOCAL) status: $STATUS | elapsed ${RUN_MIN}m | est remaining ${REMAIN_MIN}m (~$ETA_LOCAL)" | tee -a "$LOG"

  case "$STATUS" in
    running|queued|KernelWorkerStatus.RUNNING|KernelWorkerStatus.QUEUED)
      ;;
    COMPLETE|KernelWorkerStatus.COMPLETE)
      echo "[watch-r20] $(TS) ✅ COMPLETE after ${RUN_MIN}m — downloading results..." | tee -a "$LOG"
      mkdir -p "$OUT_DIR"
      cd /tmp
      timeout 900 kaggle kernels output "$KERNEL" -p /tmp/r20-out 2>&1 | tail -3 | tee -a "$LOG"
      if ls /tmp/r20-out/results.zip >/dev/null 2>&1; then
        cp /tmp/r20-out/results.zip "$OUT_DIR/results.zip"
        (cd "$OUT_DIR" && unzip -o -q results.zip 2>/dev/null || true)
        echo "[watch-r20] $(TS) ✅ adapter downloaded to $OUT_DIR" | tee -a "$LOG"
        echo "[watch-r20] $(TS) NEXT — merge LOCALLY (R20 is adapter-only by design):" | tee -a "$LOG"
        echo "[watch-r20] $(TS)   python3 scripts/build-r19-merged.py --adapter $OUT_DIR/adapter_round20 --out $OUT_DIR/merged   (pattern; adapt paths)" | tee -a "$LOG"
        echo "[watch-r20] $(TS)   (convert merged → Q4_K_M via llama-quantize --allow-requantize, then deploy-round19.sh pattern)" | tee -a "$LOG"
        echo "[watch-r20] $(TS)   deploy only with user OK — it swaps the live dspark model." | tee -a "$LOG"
      else
        echo "[watch-r20] $(TS) ⚠️ results.zip not found in kernel output — check the Output tab manually:" | tee -a "$LOG"
        echo "[watch-r20] $(TS)   https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
        # The adapter may still exist as checkpoint-*/resume/ inside the output
        # even when results.zip is absent — list what we got.
        find /tmp/r20-out -maxdepth 3 -name "*.safetensors" 2>/dev/null | head -5 | tee -a "$LOG" || true
      fi
      rm -rf /tmp/r20-out
      exit 0
      ;;
    ERROR|KernelWorkerStatus.ERROR|KernelWorkerStatus.KERNEL_WORKER_ERROR)
      echo "[watch-r20] $(TS) ❌ KERNEL ERROR — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      echo "[watch-r20] $(TS)    If it errored AFTER training (save/zip), recover the adapter from" | tee -a "$LOG"
      echo "[watch-r20] $(TS)    the kernel's checkpoint-*/resume/ dir (R19 pattern) via the Output tab." | tee -a "$LOG"
      exit 1
      ;;
    *)
      echo "[watch-r20] $(TS) unknown status: $STATUS — continuing to poll." | tee -a "$LOG"
      ;;
  esac

  [ "$ONCE" = "1" ] && exit 0
  sleep "$POLL"
done
