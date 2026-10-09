#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watch the round-14 kernel: when COMPLETE, download artifacts, recover the
# merged model (delta-merge), deploy to dspark, then let probe14wait fire the
# breadth probe.
# =============================================================================
# Log: /tmp/kaggle-watch-round14.log  (or WATCH14_LOG=<path>)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${WATCH14_LOG:-/tmp/kaggle-watch-round14.log}"
KERNEL="stevenawoods/vaca-qlora-round14"

log() { echo "[watch-r14] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "watch started — polling $KERNEL every 5 min (up to 12 h)"
for i in $(seq 1 144); do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null || echo UNKNOWN)"
  log "poll $i: $STATUS"
  case "$STATUS" in
    *COMPLETE*)
      log "✅ kernel COMPLETE — starting download"
      cd "$PROJECT_ROOT"
      python3 scripts/download-round14-merged.py all >> "$LOG" 2>&1 || { log "❌ download failed"; exit 1; }
      log "download done — delta-merge + deploy"
      python3 scripts/build-r14-delta-merge.py >> "$LOG" 2>&1 || { log "❌ delta-merge failed"; exit 1; }
      tmux kill-session -t deploy14 2>/dev/null || true
      tmux new-session -d -s deploy14 \
        "cd $PROJECT_ROOT && bash scripts/deploy-round14.sh > /tmp/deploy-r14.log 2>&1"
      log "deploy started in tmux:deploy14 (log /tmp/deploy-r14.log) — verifying deploy outcome"
      # Wait for the deploy to land (dspark-target.env -> .R14. + health OK) or
      # for the deploy session to die — a failed deploy must be LOUD, not leave
      # probe14wait armed silently for 12 h.
      for v in $(seq 1 30); do
        sleep 30
        if grep -q '\.R14\.' "$PROJECT_ROOT/scripts/dspark-target.env" 2>/dev/null; then
          HEALTH="$(curl -s -m 8 http://127.0.0.1:8000/v1/health 2>/dev/null | grep -o '"status":"ok"' || true)"
          if [ -n "$HEALTH" ]; then
            log "✅ R14 deploy verified (target + health OK) — probe14wait will fire the probe"
            exit 0
          fi
        fi
        if ! tmux has-session -t deploy14 2>/dev/null; then
          log "❌ deploy14 session ended without R14 health — check /tmp/deploy-r14.log"
          exit 1
        fi
      done
      log "❌ deploy not verified within 15 min — check /tmp/deploy-r14.log + tmux:deploy14"
      exit 1
      ;;
    *ERROR*|*CANCELED*|*FAILED*)
      log "❌ kernel status: $STATUS"
      exit 1
      ;;
  esac
  sleep 300
done
log "⏰ timed out after 12 h — kernel never COMPLETED"
exit 1
