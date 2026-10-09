#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# probe-r14-wait.sh — run the R14 dual-gate probe as soon as R14 is live.
# =============================================================================
# Waits (polling every 60s, up to 12 h) until:
#   * scripts/dspark-target.env points at the R14 GGUF (contains ".R14.")
#   * dspark :8000 health reports ok
# then runs scripts/probe-r14-3d.py (12-app battery, raw + repaired gates) in
# tmux:probe14.
#
# Log: /tmp/probe-r14-wait.log
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${PROBE_WAIT_LOG:-/tmp/probe-r14-wait.log}"
TARGET_ENV="$PROJECT_ROOT/scripts/dspark-target.env"

log() { echo "[probe14-wait] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "probe trigger armed — waiting for dspark to serve R14..."
for i in $(seq 1 720); do
  TARGET="$(grep -o '\.R14\.' "$TARGET_ENV" 2>/dev/null || true)"
  if [ -n "$TARGET" ]; then
    HEALTH="$(curl -s -m 8 http://127.0.0.1:8000/v1/health 2>/dev/null | grep -o '"status":"ok"' || true)"
    if [ -n "$HEALTH" ]; then
      log "✅ dspark serving R14 (env target confirmed) + health OK — firing probe"
      tmux kill-session -t probe14 2>/dev/null || true
      if tmux new-session -d -s probe14 \
        "cd $PROJECT_ROOT && python3 $PROJECT_ROOT/scripts/probe-r14-3d.py > /tmp/probe-r14-3d.log 2>&1"; then
        log "probe launched in tmux:probe14 — log /tmp/probe-r14-3d.log"
      else
        log "❌ tmux launch FAILED — probe not started. Run manually: python3 scripts/probe-r14-3d.py"
        exit 1
      fi
      exit 0
    fi
    log "R14 target present but health not OK yet (still warming up)..."
  fi
  sleep 60
done

log "⏰ timed out after 12 h — R14 never confirmed on dspark. Check: cat $TARGET_ENV; kaggle kernels status"
exit 1
