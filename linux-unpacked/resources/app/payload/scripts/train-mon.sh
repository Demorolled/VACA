#!/usr/bin/env bash
# train-mon.sh — one-shot status snapshot for R23 training.
# Used by train-mon-loop.sh (persistent monitor) and for one-off checks.
LOG="${1:-training/cloud/round23-train.log}"
TS="$(date '+%H:%M:%S')"
echo "════════ R23 TRAINING MONITOR  ($TS) ════════"
if pgrep -f "train_r23.py --data" >/dev/null 2>&1; then
  echo "STATUS : 🟢 RUNNING"
else
  echo "STATUS : ⚪ not running"
fi
echo
echo "── progress ──"
if [ -f "$LOG" ]; then
  # Step bar line (last one) + latest loss/learning-rate line
  tr '\r' '\n' < "$LOG" | grep -E "it/s\]" | tail -1
  grep -oE "\{'loss': [0-9.]+" "$LOG" | tail -1
  grep -oE "step [0-9]+" "$LOG" | tail -1
else
  echo "(no log yet)"
fi
echo
echo "── GPUs ──"
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null
echo
echo "── last log line ──"
tail -1 "$LOG" 2>/dev/null | cut -c1-160
