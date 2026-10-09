#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DSpark GGUF Server (OpenAI-compatible) — launcher
#
# Starts the OpenAI-compatible server on port 8000. Target defaults to the
# tuned 14B GGUF (Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M) via
# scripts/dspark-target.env when present; falls back to qwen2.5-7b-instruct-
# uncensored in Ollama. Optional draft model (qwen2.5-coder:0.5b).
# This is NOT a speculative-decoding accelerator: on llama-cpp-python 0.3.x the
# draft path measures ~parity-to-slower than no draft (~56 vs ~61 tok/s), so
# draft mode is experimental. Uses models already installed in Ollama — no
# downloads.
#
# Draft mode (DSPARK_DRAFT_MODE env, default: none — fastest, ~57-61 tok/s):
#   none   — no drafter (default; fastest).
#   lookup — built-in n-gram drafter, no extra model (~37 tok/s).
#   model  — real drafter (qwen2.5-coder:0.5b). Measured ~56 tok/s vs ~61 with
#            none on the tuned R16 — parity-to-slightly-slower, NO real
#            speedup on this hardware/binding (llama-cpp-python 0.3.x re-evals
#            the full context per draft step). Experimental opt-in via
#            `DSPARK_DRAFT_MODE=model ./scripts/start-dspark.sh --background`.
#
# Multi-GPU split (measured on the R20 14B Q4_K_M, 3× RTX 3060 12GB):
#   default --split-mode layer --tensor-split 0.34,0.33,0.33 --flash-attn.
#   The 3-GPU split uses ALL GPUs: prefill ~1860 tok/s vs ~1480 on 2 GPUs
#   (+26%, ~2.4s vs ~3.0s per 4.4K-token app call), decode ~34.7 tok/s
#   unchanged. Draft mode (DSPARK_DRAFT_MODE=model) measured SLOWER (29.7
#   vs 34.6 tok/s) on llama-cpp-python 0.3.x, so it stays off. Override via
#   DSPARK_SPLIT_MODE / DSPARK_TENSOR_SPLIT / DSPARK_FLASH_ATTN=0.
#
# Usage:
#   ./scripts/start-dspark.sh                  # foreground
#   DSPARK_DRAFT_MODE=none ./scripts/start-dspark.sh --background
#   ./scripts/start-dspark.sh --stop
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${DSPARK_PORT:-8000}"
# Bind address. 127.0.0.1 (default) is loopback-only; set DSPARK_HOST=0.0.0.0
# to expose the OpenAI-compatible API on the LAN (e.g. the control computer's
# VACA talking to this machine's model).
HOST="${DSPARK_HOST:-127.0.0.1}"
DRAFT_MODE="${DSPARK_DRAFT_MODE:-none}"
SPLIT_MODE="${DSPARK_SPLIT_MODE:-layer}"
# The 3-way split was tuned for the remote 3×RTX 3060 box; dspark_server.py
# drops it automatically when the machine has fewer GPUs than split entries.
TENSOR_SPLIT="${DSPARK_TENSOR_SPLIT:-0.34,0.33,0.33}"
N_BATCH="${DSPARK_N_BATCH:-512}"
N_CTX="${DSPARK_N_CTX:-16384}"
# 'auto' (default) fits the model to the visible VRAM — boots on this 6GB box
# and on the 3×12GB remote box alike. Override with DSPARK_N_GPU_LAYERS=-1.
N_GPU_LAYERS="${DSPARK_N_GPU_LAYERS:-auto}"
# Spec mode: serve the target WITH the trained DSpark draft head (llama-server
# --spec-type draft-dspark). Set DSPARK_SPEC_DRAFT to a GGUF to enable.
SPEC_DRAFT="${DSPARK_SPEC_DRAFT:-}"
SPEC_N_MAX="${DSPARK_SPEC_N_MAX:-4}"
SPEC_BIN="${DSPARK_SPEC_BIN:-}"
FLASH_ATTN=0
if [ "${DSPARK_FLASH_ATTN:-1}" != "0" ]; then FLASH_ATTN=1; fi
# Optional override: point dspark at a tuned GGUF (abs path or ollama name).
# Priority: DSPARK_TARGET env → persisted scripts/dspark-target.env → stock.
# The env file is written by scripts/deploy-tuned-dspark.sh so ANY launch path
# (including the backend's DSPARK_AUTOSTART) picks up the tuned model.
TARGET="${DSPARK_TARGET:-}"
if [ -z "$TARGET" ] && [ -f "scripts/dspark-target.env" ]; then
  # shellcheck disable=SC1091
  . "scripts/dspark-target.env" 2>/dev/null || true
  TARGET="${DSPARK_TARGET:-}"
fi
TARGET="${TARGET:-qwen2.5-7b-instruct-uncensored:latest}"
# Model id reported by the API (health /v1/models). Empty (default) → dspark
# reports the GGUF basename; set DSPARK_MODEL_ID to override (deploy scripts
# pass explicit ids when they launch dspark_server.py directly).
MODEL_ID="${DSPARK_MODEL_ID:-}"
LOG_FILE="scripts/dspark.log"
PID_FILE="scripts/dspark.pid"

SPEC_ARGS=()
if [ -n "$SPEC_DRAFT" ]; then
  SPEC_ARGS=(--spec-draft "$SPEC_DRAFT" --spec-n-max "$SPEC_N_MAX")
  [ -n "$SPEC_BIN" ] && SPEC_ARGS+=(--spec-bin "$SPEC_BIN")
fi

start_server() {
  echo "🚀 Starting DSpark server on port ${PORT}..."
  echo "   target: ${TARGET}"
  echo "   draft:  qwen2.5-coder:0.5b (380 MB) — mode: ${DRAFT_MODE}"
  [ -n "$SPEC_DRAFT" ] && echo "   spec:   DSpark draft ${SPEC_DRAFT} (n_max=${SPEC_N_MAX})"
  exec python3 scripts/dspark_server.py \
    --target "$TARGET" \
    --draft qwen2.5-coder:0.5b \
    --port "$PORT" \
    --host "$HOST" \
    --n-ctx "$N_CTX" \
    --n-batch "$N_BATCH" \
    --n-gpu-layers "$N_GPU_LAYERS" \
    --draft-mode "$DRAFT_MODE" \
    --split-mode "$SPLIT_MODE" \
    --tensor-split "$TENSOR_SPLIT" \
    --model-id "$MODEL_ID" \
    $([ "$FLASH_ATTN" = 1 ] && echo --flash-attn) \
    "${SPEC_ARGS[@]}"
}

case "${1:-}" in
  --background)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "DSpark server already running (pid $(cat "$PID_FILE"), port ${PORT})."
      exit 0
    fi
    if command -v setsid >/dev/null 2>&1; then
      # Detach into a NEW session (setsid -f) so the server survives the
      # process-group cleanup of a short-lived launching shell. `nohup` alone
      # leaves the child in the launching shell's process group, so it dies
      # with that shell. The pid is written by the detached child (before it
      # execs python) so the pid file always holds the real python pid, never
      # a transient setsid wrapper.
      setsid -f bash -c '
        echo $$ > "$1"
        exec python3 scripts/dspark_server.py \
          --target "$2" \
          --draft qwen2.5-coder:0.5b \
          --port "$3" \
          --host "${16}" \
          --n-ctx "${10}" \
          --n-batch "$9" \
          --n-gpu-layers "${11}" \
          --draft-mode "$4" \
          --split-mode "$6" \
          --tensor-split "$7" \
          $([ "$8" = 1 ] && echo --flash-attn) \
          ${12:+--spec-draft "${12}"} \
          ${13:+--spec-n-max "${13}"} \
          ${14:+--spec-bin "${14}"} \
          --model-id "${15}" \
          > "$5" 2>&1
      ' _ "$PID_FILE" "$TARGET" "$PORT" "$DRAFT_MODE" "$LOG_FILE" "$SPLIT_MODE" "$TENSOR_SPLIT" "$FLASH_ATTN" "$N_BATCH" "$N_CTX" "$N_GPU_LAYERS" "$SPEC_DRAFT" "$SPEC_N_MAX" "$SPEC_BIN" "$MODEL_ID" "$HOST"
    else
      nohup python3 scripts/dspark_server.py \
        --target "$TARGET" \
        --draft qwen2.5-coder:0.5b \
        --port "$PORT" \
        --host "$HOST" \
        --n-ctx "$N_CTX" \
        --n-gpu-layers "$N_GPU_LAYERS" \
        --draft-mode "$DRAFT_MODE" \
        --split-mode "$SPLIT_MODE" \
        --tensor-split "$TENSOR_SPLIT" \
        --model-id "$MODEL_ID" \
        $([ "$FLASH_ATTN" = 1 ] && echo --flash-attn) \
        "${SPEC_ARGS[@]}" \
        > "$LOG_FILE" 2>&1 &
      echo $! > "$PID_FILE"
    fi
    echo "✅ DSpark server starting in background (mode=${DRAFT_MODE}). Log: $LOG_FILE"
    # Wait until the server is actually healthy so the pid file isn't misleading.
    for _ in $(seq 1 60); do
      if curl -s --max-time 2 "http://127.0.0.1:${PORT}/v1/health" >/dev/null 2>&1; then
        echo "   Health check OK — server ready on port ${PORT}."
        break
      fi
      sleep 5
    done
    ;;
  --stop)
    if [ -f "$PID_FILE" ]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null && echo "Stopped DSpark server." || echo "Not running."
      rm -f "$PID_FILE"
    else
      echo "No DSpark server running."
    fi
    ;;
  *)
    start_server
    ;;
esac
