#!/usr/bin/env bash
# start-puzzle-trainer.sh — serve the R20 14B on :8002 and run the Puzzle-RAG trainer
# ==============================================================================
#   The app's dspark (R28) keeps :8000.  The puzzle trainer plays against the
#   R20 GGUF on a SEPARATE port (:8002) so training never disturbs the app.
#
# Usage:
#   bash scripts/start-puzzle-trainer.sh --rounds 3 [trainer args...]
#     any args after --rounds are passed to puzzle_trainer.py
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Per-instance overrides — lets a 2nd trainer run in parallel (R28 on :8004):
#   PUZZLE_MODEL=<gguf>  PUZZLE_PORT=8004  PUZZLE_TAG=r28  PUZZLE_OUT=train-r28
MODEL="${PUZZLE_MODEL:-$ROOT/models/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf}"
PORT="${PUZZLE_PORT:-8002}"
TAG="${PUZZLE_TAG:-r20}"
OUT_SUB="${PUZZLE_OUT:-puzzle-r30}"
N_GPU_LAYERS="${DSPARK_N_GPU_LAYERS:-auto}"

# ── 1. serve R20 on :8002 (if not already) ──────────────────────────────────
if curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
  echo "[puzzle] R20 already serving on :$PORT — reusing"
else
  echo "[puzzle] starting dspark (R20) on :$PORT …"
  cd "$ROOT" || exit 1
  # second instance: smaller ctx + let auto-fit find room next to R28
  CTX=8192
  [ "$PORT" != "8002" ] && CTX=8192
  setsid nohup python3 scripts/dspark_server.py \
    --target "$MODEL" \
    --port "$PORT" \
    --n-ctx "$CTX" --n-batch 512 \
    --n-gpu-layers "$N_GPU_LAYERS" \
    --flash-attn \
    > "data/puzzle-dspark-$PORT-$TAG.log" 2>&1 < /dev/null &
  for i in $(seq 1 60); do
    if curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
      echo "[puzzle] R20 up on :$PORT (${i}0s)"
      break
    fi
    sleep 10
  done
  if ! curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    echo "[puzzle] ❌ R20 failed to come up — tail data/puzzle-dspark-$PORT.log"
    tail -30 "data/puzzle-dspark-$PORT.log"
    exit 1
  fi
fi

# ── 2. run the trainer (all CLI args pass straight through) ────────────────
cd "$ROOT" || exit 1
exec python3 -u scripts/puzzle_trainer.py \
  --llm-url "http://127.0.0.1:$PORT/v1/chat/completions" \
  --out-dir "$ROOT/training/cloud/$OUT_SUB" \
  "$@"
