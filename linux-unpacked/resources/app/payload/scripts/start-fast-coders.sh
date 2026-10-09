#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Fast-coder tiers: two Qwen2.5-Coder-0.5B servers (same Ollama GGUF, shared).
#
#   coderGpu1 (:11437) — 0.5B fully on GPU 1 (CUDA_VISIBLE_DEVICES=1)
#   coderCpu  (:11436) — 0.5B on CPU, limited to 2 threads (--n-threads 2)
#
# The 14B (dspark :8000) is the band leader: it plans/reasons and delegates
# simple standalone files to these tiers via translator.reasonFast() (chain:
# GPU1 0.5B → 1.5B on GPU0 → CPU 0.5B → 14B). The backend probes the tiers
# every 30s, so no backend restart is needed after this script runs.
#
# Usage:
#   ./scripts/start-fast-coders.sh              # start both (idempotent)
#   ./scripts/start-fast-coders.sh --stop       # stop both
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
MODEL="${FAST_CODER_MODEL:-qwen2.5-coder:0.5b}"
CPU_PID_FILE="scripts/fast-coder-cpu.pid"
GPU_PID_FILE="scripts/fast-coder-gpu1.pid"
CPU_LOG="scripts/fast-coder-cpu.log"
GPU_LOG="scripts/fast-coder-gpu1.log"

start_one() {
  local pid_file="$1" log="$2" port="$3" extra="$4"
  if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "  already running (pid $(cat "$pid_file"), port ${port}) — skipping"
    return 0
  fi
  setsid -f bash -c '
    echo $$ > "$1"
    cd "$2"
    exec $3 python3 scripts/dspark_server.py \
      --target "$4" \
      --port "$5" \
      --n-gpu-layers "$6" \
      --n-threads "$7" \
      --n-ctx 8192 \
      --draft-mode none \
      --model-id "$4" \
      > "$8" 2>&1
  ' _ "$pid_file" "$PWD" "$EXTRA_ENV" "$MODEL" "$port" "$EXTRA_LAYERS" "$EXTRA_THREADS" "$log"
}

echo "🚀 Starting fast-coder tiers (${MODEL}):"
echo "   coderGpu1 — 0.5B on GPU 1, port 11437"
EXTRA_ENV="env CUDA_VISIBLE_DEVICES=1" EXTRA_LAYERS="-1" EXTRA_THREADS="0" \
  start_one "$GPU_PID_FILE" "$GPU_LOG" 11437
echo "   coderCpu  — 0.5B on CPU (2 threads), port 11436"
EXTRA_ENV="" EXTRA_LAYERS="0" EXTRA_THREADS="2" \
  start_one "$CPU_PID_FILE" "$CPU_LOG" 11436

for port in 11437 11436; do
  for _ in $(seq 1 30); do
    if curl -s --max-time 2 "http://127.0.0.1:${port}/v1/health" >/dev/null 2>&1; then
      echo "   port ${port}: health OK"
      break
    fi
    sleep 2
  done
done
echo "✅ Fast-coder tiers ready. Backend picks them up within 30s (probe)."