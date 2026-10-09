#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# launch-sky1-slice.sh — run the 2,000-row Sky1 SFT slice on the agent's 3 GPUs.
# =============================================================================
# Launch fully detached so it survives SSH/VNC disconnects:
#   setsid bash scripts/launch-sky1-slice.sh > /home/llmlab/vaca-training/launch.log 2>&1 &
#
# Reads config from env (defaults are the fast-slice run):
#   VACA_MAX_TRAIN   rows to train (default 2000)
#   VACA_OUT         output dir     (default /home/llmlab/vaca-training/sky1-slice)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

MAX="${VACA_MAX_TRAIN:-2000}"
SEQ="${VACA_SEQ:-512}"
MEM="${VACA_MEM_GB:-6}"
OUT="${VACA_OUT:-/home/llmlab/vaca-training/sky1-slice}"
ROOT="/home/llmlab/Desktop/visual-ai-architect"
TRAINER="$ROOT/backend/scripts/train_sky1_agent_3gpu.py"
LOG="$OUT.log"

mkdir -p "$OUT" "$(dirname "$LOG")"
source /home/llmlab/vaca-venv/bin/activate
cd "$ROOT"

echo "[$(date '+%F %T')] starting Sky1 slice: MAX_TRAIN=$MAX SEQ=$SEQ MEM=$MEM → $OUT" >> "$LOG"
VACA_MAX_TRAIN="$MAX" VACA_SEQ="$SEQ" VACA_MEM_GB="$MEM" VACA_OUT="$OUT" \
  python3 "$TRAINER" >> "$LOG" 2>&1
echo "[$(date '+%F %T')] trainer exited with code $?" >> "$LOG"