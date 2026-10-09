#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watch the round-16 kernel: when COMPLETE, download artifacts, build the
# merged model (base + adapter), deploy to dspark, then fire a probe.
# =============================================================================
# Log: /tmp/kaggle-watch-round16.log  (or WATCH16_LOG=<path>)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${WATCH16_LOG:-/tmp/kaggle-watch-round16.log}"
KERNEL="stevenawoods/vaca-r16-anti-fence-clean-round-resume-r15"

log() { echo "[watch-r16] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "watch started — polling $KERNEL every 5 min (up to 12 h)"
for i in $(seq 1 144); do
  STATUS="$(timeout 30 kaggle kernels status "$KERNEL" 2>/dev/null || echo UNKNOWN)"
  log "poll $i: $STATUS"
  case "$STATUS" in
    *COMPLETE*)
      log "✅ kernel COMPLETE — starting download"
      cd "$PROJECT_ROOT"
      python3 scripts/download-round16-merged.py all >> "$LOG" 2>&1 || { log "❌ download failed"; exit 1; }
      log "download done — build merged + deploy"
      python3 scripts/build-r16-merged.py >> "$LOG" 2>&1 || { log "❌ merge failed"; exit 1; }
      tmux kill-session -t deploy16 2>/dev/null || true
      tmux new-session -d -s deploy16 \
        "cd $PROJECT_ROOT && bash scripts/deploy-round16.sh > /tmp/deploy-r16.log 2>&1"
      log "deploy started in tmux:deploy16 (log /tmp/deploy-r16.log) — verifying deploy outcome"
      for v in $(seq 1 30); do
        sleep 30
        if grep -q '\.R16\.' "$PROJECT_ROOT/scripts/dspark-target.env" 2>/dev/null; then
          HEALTH="$(curl -s -m 8 http://127.0.0.1:8000/v1/health 2>/dev/null | grep -o '"status":"ok"' || true)"
          if [ -n "$HEALTH" ]; then
            log "✅ R16 deploy verified (target + health OK) — firing R16 probe"
            tmux kill-session -t probe16 2>/dev/null || true
            tmux new-session -d -s probe16 \
              "cd $PROJECT_ROOT && python3 scripts/probe-r16.py > /tmp/probe-r16.log 2>&1"
            log "R16 probe launched in tmux:probe16"
            exit 0
          fi
        fi
        if ! tmux has-session -t deploy16 2>/dev/null; then
          log "❌ deploy16 session ended without R16 health — check /tmp/deploy-r16.log"
          exit 1
        fi
      done
      log "❌ deploy not verified within 15 min — check /tmp/deploy-r16.log + tmux:deploy16"
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
