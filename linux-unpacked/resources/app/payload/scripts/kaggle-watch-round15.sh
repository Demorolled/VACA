#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watch the round-15 kernel: when COMPLETE, download artifacts, recover the
# merged model (delta-merge), deploy to dspark, then fire the R15 GUI probe.
# =============================================================================
# Log: /tmp/kaggle-watch-round15.log  (or WATCH15_LOG=<path>)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${WATCH15_LOG:-/tmp/kaggle-watch-round15.log}"
KERNEL="stevenawoods/vaca-qlora-round15"

log() { echo "[watch-r15] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "watch started — polling $KERNEL every 5 min (up to 12 h)"
for i in $(seq 1 144); do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null || echo UNKNOWN)"
  log "poll $i: $STATUS"
  case "$STATUS" in
    *COMPLETE*)
      log "✅ kernel COMPLETE — starting download"
      cd "$PROJECT_ROOT"
      python3 scripts/download-round15-merged.py all >> "$LOG" 2>&1 || { log "❌ download failed"; exit 1; }
      log "download done — delta-merge + deploy"
      python3 scripts/build-r15-delta-merge.py >> "$LOG" 2>&1 || { log "❌ delta-merge failed"; exit 1; }
      tmux kill-session -t deploy15 2>/dev/null || true
      tmux new-session -d -s deploy15 \
        "cd $PROJECT_ROOT && bash scripts/deploy-round15.sh > /tmp/deploy-r15.log 2>&1"
      log "deploy started in tmux:deploy15 (log /tmp/deploy-r15.log) — verifying deploy outcome"
      for v in $(seq 1 30); do
        sleep 30
        if grep -q '\.R15\.' "$PROJECT_ROOT/scripts/dspark-target.env" 2>/dev/null; then
          HEALTH="$(curl -s -m 8 http://127.0.0.1:8000/v1/health 2>/dev/null | grep -o '"status":"ok"' || true)"
          if [ -n "$HEALTH" ]; then
            log "✅ R15 deploy verified (target + health OK) — firing R15 GUI probe"
            tmux kill-session -t probe15gui 2>/dev/null || true
            tmux new-session -d -s probe15gui \
              "cd $PROJECT_ROOT && python3 scripts/probe-r15-gui.py > /tmp/probe-r15-gui.log 2>&1"
            log "R15 GUI probe launched in tmux:probe15gui"
            exit 0
          fi
        fi
        if ! tmux has-session -t deploy15 2>/dev/null; then
          log "❌ deploy15 session ended without R15 health — check /tmp/deploy-r15.log"
          exit 1
        fi
      done
      log "❌ deploy not verified within 15 min — check /tmp/deploy-r15.log + tmux:deploy15"
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
