#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy the freshly-trained GGUF to dspark
# =========================================
# Watches for the QLoRA run to FINISH (training process exits — the GGUF export
# runs inside the training process, so exit == export done). Then:
#   1. Waits for the new .gguf to be size/mtime-stable (60s window)
#   2. Sanity-checks the file size (7B q4_k_m is ~4.4GB; refuse tiny partials)
#   3. Copies it into models/ (alongside the stock GGUF — nothing overwritten)
#   4. Stops dspark (kills by pid file AND port as a fallback)
#   5. Restarts dspark with DSPARK_TARGET=<tuned gguf path> (dspark resolves
#      direct file paths first, so no ollama manifest surgery needed)
#   6. Health-checks /v1/health
#
# Prefers the q4_k_m export (matches the stock model's quantization) over any
# f16/other intermediates Unsloth may also write.
#
# Usage:
#   ./scripts/deploy-tuned-dspark.sh --watch     # wait for training, then deploy
#   ./scripts/deploy-tuned-dspark.sh --now <gguf> # deploy an existing gguf
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRAIN_DIR="$PROJECT_ROOT/training/gui_trainer/models"
# Unsloth's save_pretrained_gguf special-cases a "models" output dir and
# hoists the export into <parent>/models_gguf/ instead — check both.
GGUF_DIR="$PROJECT_ROOT/training/gui_trainer/models_gguf"
MODELS_DIR="$PROJECT_ROOT/models"
PORT="${DSPARK_PORT:-8000}"
START_TS="$(date +%s)"
MIN_GGUF_BYTES=$((1 * 1024 * 1024 * 1024))  # refuse anything under 1GB

stop_dspark() {
  echo "🛑 Stopping dspark (pid file)..."
  bash "$SCRIPT_DIR/start-dspark.sh" --stop 2>/dev/null || true
  # Fallback: kill whatever is bound to the dspark port
  local pids
  pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "   Port $PORT held by: $pids — killing..."
    kill $pids 2>/dev/null || true
    sleep 2
    pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
    [ -z "$pids" ] || kill -9 $pids 2>/dev/null || true
  fi
}

# Require size AND mtime unchanged across 6 polls (10s apart = 60s window).
wait_stable() {
  local file="$1"
  local psize="" pmtime="" csize="" cmtime="" stable=0
  echo "   Waiting for $file to finish writing (60s stability window)..."
  while [ "$stable" -lt 6 ]; do
    csize="$(stat -c %s "$file" 2>/dev/null || echo 0)"
    cmtime="$(stat -c %Y "$file" 2>/dev/null || echo 0)"
    if [ "$csize" = "$psize" ] && [ "$cmtime" = "$pmtime" ] && [ "$csize" -gt 0 ]; then
      stable=$((stable + 1))
    else
      stable=0
    fi
    psize="$csize"
    pmtime="$cmtime"
    sleep 10
  done
  echo "   File stable: $csize bytes."
}

pick_newest_gguf() {
  # Prefer q4_k_m; otherwise newest .gguf newer than script start.
  # Globs both layout dirs (models/ legacy, models_gguf/ current).
  local q4="" newest="" f mt
  for dir in "$TRAIN_DIR" "$GGUF_DIR"; do
    for f in "$dir"/*.gguf; do
      [ -f "$f" ] || continue
      mt="$(stat -c %Y "$f")"
      [ "$mt" -ge "$START_TS" ] || continue
      newest="$f"
      case "$(basename "$f")" in
        *q4_k_m*) q4="$f" ;;
      esac
    done
  done
  [ -n "$q4" ] && { echo "$q4"; return; }
  echo "$newest"
}

training_running() {
  pgrep -f 'launch-qlora' >/dev/null 2>&1
}

deploy() {
  local gguf="$1"
  if [ ! -f "$gguf" ]; then
    echo "❌ GGUF not found: $gguf"
    exit 1
  fi
  wait_stable "$gguf"

  local size; size="$(stat -c %s "$gguf" 2>/dev/null || echo 0)"
  if [ "$size" -lt "$MIN_GGUF_BYTES" ]; then
    echo "❌ $gguf is only $size bytes (< 1GB) — refusing to serve a partial/crashed export."
    echo "   Training may have failed mid-export. Check data/qlora-campaign50-ddp.log"
    exit 1
  fi

  local name; name="$(basename "$gguf")"
  local dest="$MODELS_DIR/$name"

  echo "📦 Copying tuned model → $dest ($size bytes)"
  cp -f "$gguf" "$dest"

  # Persist the target so ANY future dspark launch (backend DSPARK_AUTOSTART,
  # manual restarts) serves the tuned model, not the stock ollama one.
  echo "DSPARK_TARGET=$dest" > "$SCRIPT_DIR/dspark-target.env"
  echo "💾 Persisted target → $SCRIPT_DIR/dspark-target.env"

  stop_dspark

  echo "🚀 Starting dspark with DSPARK_TARGET=$dest"
  DSPARK_TARGET="$dest" bash "$SCRIPT_DIR/start-dspark.sh" --background

  echo "🔎 Health check:"
  curl -s --max-time 5 "http://127.0.0.1:${PORT}/v1/health" || echo "⚠️  Health check failed"
  echo
  echo "✅ dspark now serving: $dest"

  # Auto-cleanup (default ON): this round's safetensors exports + duplicate
  # GGUFs are superseded by the deployed models/ copy — deleting them keeps a
  # round's footprint at ~5GB (adapter + one F16) instead of ~45GB. Keeps the
  # newest adapter + F16; never touches models/ or a live target. Opt out per
  # run with CLEANUP_ROUND=0, or use --older-only to keep the newest round's
  # safetensors until the next round lands.
  if [ "${CLEANUP_ROUND:-1}" = "1" ]; then
    echo "🧹 Cleaning superseded round artifacts..."
    python3 "$SCRIPT_DIR/cleanup-round-artifacts.py" --apply || echo "⚠️  cleanup round artifacts failed (non-fatal)"
  else
    echo "🧹 Round artifacts left as-is (CLEANUP_ROUND=0)."
  fi
}

if [ "${1:-}" = "--now" ]; then
  [ -n "${2:-}" ] || { echo "Usage: deploy-tuned-dspark.sh --now <gguf>"; exit 1; }
  deploy "$(realpath "$2")"
  exit 0
fi

if [ "${1:-}" = "--watch" ]; then
  # Self-register PID so we can be stopped reliably without pkill -f (which
  # risks matching the launching shell). Written before any long loop.
  echo $$ > "$PROJECT_ROOT/data/deploy-watch.pid"
  MAX_WAIT="${MAX_WAIT:-7200}"  # default 2h; 0 = wait forever
  echo "👀 Waiting for training to finish (started $(date -d @$START_TS), max ${MAX_WAIT}s)..."
  waited=0
  while true; do
    if training_running; then
      sleep 30
      waited=$((waited + 30))
    else
      gguf="$(pick_newest_gguf)"
      if [ -n "$gguf" ]; then
        echo "✨ Training finished. Found GGUF: $gguf"
        deploy "$gguf"
        exit 0
      fi
      echo "   Training not running yet & no new GGUF — still waiting..."
      sleep 60
      waited=$((waited + 60))
    fi
    if [ "$MAX_WAIT" -gt 0 ] && [ "$waited" -ge "$MAX_WAIT" ]; then
      echo "❌ No GGUF appeared within ${MAX_WAIT}s — training may have failed."
      echo "   Check: tail -50 data/qlora-campaign50-ddp.log"
      exit 1
    fi
  done
fi

echo "Usage: $0 --watch | --now <gguf>"
exit 1
