#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# launch-r23.sh — build the R23 corpus and train on all 3 GPUs (detached).
#   Run ON THE AGENT (GPU box):
#     bash scripts/launch-r23.sh
#   Monitor:
#     tail -f training/cloud/round23-train.log
#     nvidia-smi                       # all 3 GPUs should show ~9-11 GB + high util
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

VENV_BIN=llm-training-app/.venv/bin
LOG=training/cloud/round23-train.log
OUT=training/cloud/out/round23
TS="$(date +%Y%m%d-%H%M)"

echo "── [1/4] freeing disk (superseded round21 artifacts) ──"
rm -rf training/cloud/out/round21 training/cloud/out/round21_gguf 2>/dev/null || true
df -h / | tail -1

echo "── [2/4] building bible-code segment ──"
python3 scripts/build-r23-bible-code.py --max-rows 400

echo "── [3/4] merging R23 dataset ──"
python3 scripts/merge-round23.py
wc -l training/cloud/round23-all.jsonl

echo "── [4/4] launching 3-GPU training (detached) ──"
echo "log: $LOG"
# Single-process model-parallel (device_map=balanced_low_0 across all 3 GPUs) —
# the proven pattern on this box. NOT torchrun/DDP: train_r23.py loads the 14B
# itself with accelerate's device_map. seq 1280 = R20's p99 prompt length (2048 OOMs).
setsid "$VENV_BIN/python" train_r23.py \
  --data training/cloud/round23-all.jsonl \
  --output-dir "$OUT" \
  --max-seq-length 1280 \
  --epochs 2 \
  --lr 5e-5 \
  > "$LOG" 2>&1 < /dev/null &

echo "launched pid $! — first output in ~30-60s (base model load + tokenize)."
echo "quick sanity: sleep 60 && tail -30 $LOG"
