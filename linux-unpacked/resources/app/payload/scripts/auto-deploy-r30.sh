#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto-deploy-r30.sh — deploy R30 the moment agent training finishes
# =============================================================================
# The R30 round trains on the agent (3× 3060, /home/llmlab/vaca-r30/). When the
# trainer exits this watcher runs the proven chain:
#   1. wait     : for train_r30_agent.py to exit AND final/ adapter to appear
#   2. merge    : build-r30-merged.py --merge-only (CPU fp16 → clean fp16)
#   3. convert  : llama.cpp convert_hf_to_gguf.py → Q8_0
#   4. quant    : llama-quantize → Q4_K_M (same quantization as R23/R28)
#   5. ollama   : create vaca-r30:latest from the Q4 GGUF (bare-prompt template,
#                 same as vaca-r25-10h-local — the model the retention eval used)
#   6. done     : write round30-deploy.done marker + summary
# Log: training/cloud/round30-deploy.log (tail -f from anywhere)
#
# Usage (ON THE AGENT, detached — survives SSH drops):
#   setsid bash scripts/auto-deploy-r30.sh > training/cloud/round30-deploy.log 2>&1 < /dev/null &
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root on the agent

MERGE_PY="scripts/build-r30-merged.py"
MERGE_VENV="/home/llmlab/vaca-train-venv/bin/python"   # the venv that trained R30
ROUND30="training/cloud/out/round30"
MERGED="$ROUND30/merged"
ADAPTER="/home/llmlab/vaca-r30/output/round30/final"
GGUF_DIR="$ROUND30/gguf"
GGUF_Q8="$GGUF_DIR/vaca-r30.Q8_0.gguf"
GGUF_Q4="$GGUF_DIR/vaca-r30.Q4_K_M.gguf"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
QUANT="$HOME/.unsloth/llama.cpp/llama-quantize"
OLLAMA_NAME="vaca-r30"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { say "❌ $*"; exit 1; }

say "=== R30 auto-deploy watcher started $(date) ==="
say "watching for trainer exit (pgrep train_r30_agent.py)…"

# ── 0. wait for training to finish ──────────────────────────────────────────
while pgrep -f "train_r30_agent.py" >/dev/null 2>&1; do
  sleep 60
done
say "trainer process exited."

# Grace: adapter may still be flushing; wait up to 30 min for it.
waited=0
while [ ! -f "$ADAPTER/adapter_model.safetensors" ]; do
  if [ "$waited" -ge 1800 ]; then
    fail "adapter never appeared at $ADAPTER — check /home/llmlab/vaca-r30/train.log"
  fi
  sleep 60; waited=$((waited + 60))
done
say "✅ adapter found: $ADAPTER"
df -h / | tail -1

# ── 1. merge (CPU fp16, ~10-20 min) ─────────────────────────────────────────
say "── [1/4] merge LoRA → fp16 (CPU, vaca-train-venv) ──"
"$MERGE_VENV" "$MERGE_PY" --merge-only || fail "merge failed (see log above)"
df -h / | tail -1

# ── 2+3. convert + quantize (~20 min) ───────────────────────────────────────
mkdir -p "$GGUF_DIR"
say "── [2/4] convert merged fp16 → Q8_0 (~10-15 min) ──"
"$MERGE_VENV" "$CONVERT" "$MERGED" --outfile "$GGUF_Q8" --outtype q8_0 || fail "convert failed"
say "── [3/4] quantize Q8_0 → Q4_K_M (~5 min) ──"
"$QUANT" "$GGUF_Q8" "$GGUF_Q4" q4_k_m --allow-requantize || fail "quantize failed"
Q4_SIZE="$(stat -c %s "$GGUF_Q4")"
[ "$Q4_SIZE" -gt 8000000000 ] || fail "Q4 GGUF only ${Q4_SIZE} bytes — refusing to deploy partial export"
say "✅ Q4_K_M GGUF: $(du -h "$GGUF_Q4" | cut -f1)"

# ── 4. ollama create (bare {{ .Prompt }} template — matches vaca-r25-10h-local) ──
say "── [4/4] ollama create $OLLAMA_NAME ──"
cat > "$GGUF_DIR/Modelfile" <<EOF
FROM $GGUF_Q4
TEMPLATE {{ .Prompt }}
EOF
ollama create vaca-r30 -f "$GGUF_DIR/Modelfile" || fail "ollama create failed"
ollama list | grep vaca-r30 || fail "vaca-r30 not in ollama list"

# ── cleanup + done marker ───────────────────────────────────────────────────
say "── cleanup (keep Q4 GGUF + merged fp16; drop Q8 intermediate) ──"
rm -f "$GGUF_Q8"
say "  removed Q8 intermediate"
df -h / | tail -1

say "✅✅ R30 DEPLOY COMPLETE — $(date)"
echo "DEPLOY_DONE at $(date)" > "$ROUND30/round30-deploy.done"
say "  ollama model: $(ollama list | grep vaca-r30)"
