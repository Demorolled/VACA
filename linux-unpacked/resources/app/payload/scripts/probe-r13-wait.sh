#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# probe-r13-wait.sh — run the R13 breadth probe as soon as R13 is live
# =============================================================================
# Waits (polling every 60s, up to 12 h) until:
#   * scripts/dspark-target.env points at the R13 GGUF (contains ".R13.")
#   * dspark :8000 health reports ok
# then runs scripts/probe-r13-3d.py (12-app random-3D battery) in tmux:probe13.
#
# Note: the chain deploys R12 first (dspark-target.env -> .R12.), then watch13
# deploys R13 (-> .R13.). This daemon only fires on the R13 target, so it never
# probes R12.
#
# Log: /tmp/probe-r13-wait.log
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${PROBE_WAIT_LOG:-/tmp/probe-r13-wait.log}"
TARGET_ENV="$PROJECT_ROOT/scripts/dspark-target.env"

log() { echo "[probe13-wait] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "probe trigger armed — waiting for dspark to serve R13..."
for i in $(seq 1 720); do
  TARGET="$(grep -o '\.R13\.' "$TARGET_ENV" 2>/dev/null || true)"
  if [ -n "$TARGET" ]; then
    HEALTH="$(curl -s -m 8 http://127.0.0.1:8000/v1/health 2>/dev/null | grep -o '"status":"ok"' || true)"
    if [ -n "$HEALTH" ]; then
      log "✅ dspark serving R13 (env target confirmed) + health OK — firing probe"
      tmux kill-session -t probe13 2>/dev/null || true
      tmux new-session -d -s probe13 \
        "cd $PROJECT_ROOT && python3 $PROJECT_ROOT/scripts/probe-r13-3d.py > /tmp/probe-r13-3d.log 2>&1"
      log "probe launched in tmux:probe13 — log /tmp/probe-r13-3d.log"
      exit 0
    fi
    log "R13 target present but health not OK yet (still warming up)..."
  fi
  sleep 60
done

log "⏰ timed out after 12 h — R13 never confirmed on dspark. Check: cat $TARGET_ENV; kaggle kernels status"
exit 1
