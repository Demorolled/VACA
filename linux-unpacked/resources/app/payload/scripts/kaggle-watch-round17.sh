#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Round-17 watchdog: polls the R17 Kaggle kernel; on COMPLETE it downloads the
# adapter, builds the merged 14B locally, and deploys to dspark (backing up
# the 7B R16 GGUF first). Mirrors kaggle-watch-round16.sh.
# =============================================================================
#   bash scripts/kaggle-watch-round17.sh               # long-running watchdog
#   bash scripts/kaggle-watch-round17.sh --once        # single status check
#   KAGGLE_WATCH_POLL=300 bash scripts/kaggle-watch-round17.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

KERNEL="stevenawoods/vaca-qlora-round17"
LOG="${KAGGLE_WATCH_LOG:-/tmp/kaggle-watch-round17.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"   # seconds between polls (default 5 min)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ONCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1 ;;
    *) echo "❌ Unknown arg: $1 (--once)" >&2; exit 1 ;;
  esac
  shift || true
done

TS() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "[watch-r17] $(TS) started (poll ${POLL}s)" | tee -a "$LOG"

while true; do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo UNKNOWN)"
  echo "[watch-r17] $(TS) kernel status: $STATUS" | tee -a "$LOG"

  case "$STATUS" in
    COMPLETE)
      echo "[watch-r17] $(TS) ✅ COMPLETE — downloading adapter + merged..." | tee -a "$LOG"
      cd "$ROOT"
      python3 scripts/download-round17-merged.py all 2>&1 | tail -5 | tee -a "$LOG"
      echo "[watch-r17] $(TS) building merged 14B (may take ~20 min)..." | tee -a "$LOG"
      if python3 scripts/build-r17-merged.py 2>&1 | tail -3 | tee -a "$LOG"; then
        echo "[watch-r17] $(TS) deploying to dspark..." | tee -a "$LOG"
        if bash scripts/deploy-round17.sh 2>&1 | tail -5 | tee -a "$LOG"; then
          echo "[watch-r17] $(TS) ✅ R17 deployed — dspark now serves the 14B coder." | tee -a "$LOG"
        else
          echo "[watch-r17] $(TS) ❌ deploy failed — see log. Manual: bash scripts/deploy-round17.sh" | tee -a "$LOG"
        fi
      else
        echo "[watch-r17] $(TS) ❌ merge failed — see log. Manual: python3 scripts/build-r17-merged.py" | tee -a "$LOG"
      fi
      exit 0
      ;;
    RUNNING|QUEUED|PENDING)
      echo "[watch-r17] $(TS) still training — polling again in ${POLL}s" | tee -a "$LOG"
      ;;
    ERROR|CANCELED)
      echo "[watch-r17] $(TS) ❌ kernel $STATUS — check https://www.kaggle.com/code/$KERNEL" | tee -a "$LOG"
      exit 1
      ;;
    *)
      echo "[watch-r17] $(TS) status '$STATUS' — retrying in ${POLL}s" | tee -a "$LOG"
      ;;
  esac

  if [ "$ONCE" = "1" ]; then exit 0; fi
  sleep "$POLL"
done
