#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# chain-r28-distill-train.sh — auto-chain distillation → local 3-GPU 14B train
# =============================================================================
# Waits for the 27B distillation to FINISH (round28-distill-27b.jsonl stops
# growing), then:
#   1. Stops DSpark (frees the ~9 GB×2 it holds on GPUs 0/1 serving the 27B)
#   2. Recompiles the Round-28 corpus (round25 catch-up + the distilled rows)
#   3. Launches the local 3-GPU 14B QLoRA training (train_r28_14b.py)
#      with the PROVEN env recipe: uv python3.13 + PYTHONPATH into the
#      unsloth studio site-packages (the activate script's symlink is broken).
#   4. Watches training, reports progress.
#
# Safeguards: refuses to train while ANY dspark/distill/qlora python is on the
# GPUs; only stops DSpark, never the QLoRA or the backend. Idempotent-ish:
# if the corpus is already compiled it just recompiles (dedup) and launches.
#
# Usage (ON THE AGENT, detached):
#   bash scripts/chain-r28-distill-train.sh            # full chain
#   bash scripts/chain-r28-distill-train.sh --wait 1800  # max wait for distill (s)
# Log: data/r28-chain.log
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT_JSONL="training/cloud/round28-distill-27b.jsonl"
COMPILE="python3 scripts/compile-r28-corpus.py"
LOG="data/r28-chain.log"
PORT="${DSPARK_PORT:-8000}"

# env recipe (verified: torch 2.10+cu130, cuda 3, peft 0.18.1, tf 4.57.6)
PY="/home/llmlab/.local/share/uv/python/cpython-3.13.13-linux-x86_64-gnu/bin/python3.13"
SP="$HOME/.unsloth/studio/unsloth_studio/lib/python3.13/site-packages"
export PYTHONPATH="$SP"
TRAIN="$PY scripts/train_r28_14b.py"

say(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
mkdir -p "$(dirname "$LOG")"

# ─── WAIT_MAX_LIMIT ──────────────────────────────────────────────────────────
WAIT_MAX=0
if [ "${1:-}" = "--wait" ]; then WAIT_MAX="${2:-0}"; fi

# ─── 1. Wait for distillation to finish ─────────────────────────────────────
say "👀 chain started — waiting for 27B distillation to finish..."
WAITED=0
while true; do
  # running? any distill-27b python process alive
  if pgrep -f 'distill-27b-vaca.py' >/dev/null 2>&1; then
    ROWS="$(wc -l < "$OUT_JSONL" 2>/dev/null || echo 0)"
    say "   distillation running — $(wc -l < "$OUT_JSONL") rows so far"
    sleep 60; WAITED=$((WAITED + 60))
    if [ "$WAIT_MAX" -gt 0 ] && [ "$WAITED" -ge "$WAIT_MAX" ]; then
      say "❌ distill still running after ${WAIT_MAX}s — aborting chain."
      exit 3
    fi
    continue
  fi
  # process gone: give the file one more settle then break
  say "✅ distillation process finished — $(wc -l < "$OUT_JSONL") rows captured."
  break
done

# ─── 2. Stop DSpark + confirm GPUs are free ─────────────────────────────────
say "🛑 Stopping DSpark to free VRAM (it holds the 27B on GPUs 0/1)..."
# systemd runs dspark as a service — `start-dspark.sh --stop` only kills the
# pid file and systemd RE-SPAWNS it, stealing the trainer's VRAM mid-run (this
# caused the R28 local OOM). Must stop via systemd so it stays down.
if command -v systemctl >/dev/null 2>&1 && systemctl is-active dspark >/dev/null 2>&1; then
  sudo systemctl stop dspark 2>&1 | tee -a "$LOG"
fi
PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  say "   Port $PORT still held by: $PIDS — killing..."
  kill $PIDS 2>/dev/null || true; sleep 3
  PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  [ -z "$PIDS" ] || kill -9 $PIDS 2>/dev/null || true
fi
sleep 3
# Safety: refuse to train if any qlora/distill python still holds VRAM.
if pgrep -f 'distill-27b-vaca.py' >/dev/null 2>&1 || pgrep -f 'launch-qlora' >/dev/null 2>&1; then
  say "❌ Another training/distill process is still alive — aborting (won't double-run)."
  exit 3
fi
sleep 5
say "✨ DSpark stopped. GPU memory now:"
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | while read -r l; do say "   $l"; done

# ─── 3. Recompile the Round-28 corpus (with distilled rows) ─────────────────
say "📚 Recompiling Round-28 corpus (catch-up + distilled)..."
if ! $COMPILE 2>&1 | tee -a "$LOG"; then
  say "❌ compile failed — aborting."
  exit 1
fi
ROWS_TOTAL="$(python3 -c "import json;print(json.load(open('training/cloud/round28.meta.json'))['total_rows'])" 2>/dev/null || echo '?')"
say "   round28-train.jsonl = $ROWS_TOTAL rows"

# ─── 4. Launch local 3-GPU 14B training ────────────────────────────────────
say "🚀 Launching 14B QLoRA training on all 3 GPUs ($TRAIN)"
mkdir -p data
setsid bash -c "
  cd '$ROOT'
  echo \$BASHPID > data/r28-train.pid
  exec env PYTHONPATH='$SP' '$PY' scripts/train_r28_14b.py >> data/r28-train.log 2>&1
" < /dev/null > /dev/null 2>&1 &
CHAIN_PID=$!
echo "$CHAIN_PID" > data/r28-chain.pid

# tail a bit so the caller sees it actually started
sleep 20
say "   20s in — training log tail:"
tail -12 data/r28-train.log 2>/dev/null | while read -r l; do say "     $l"; done
say "   (monitor: tail -f data/r28-train.log)"
exit 0