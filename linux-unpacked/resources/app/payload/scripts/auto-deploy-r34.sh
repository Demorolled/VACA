#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto-deploy-r34.sh — deploy R34b (the correction round, 89% eval) to ollama
# =============================================================================
# R34b is the correction round trained on TOP OF R33 merged (telescoping chain
# base → R33 → R34b). The merge to clean fp16 already completed manually
# (build-r34b-merged.py → training/cloud/out/round34b/merged). This script
# finishes the proven chain (same as auto-deploy-r33.sh):
#   1. convert  : llama.cpp convert_hf_to_gguf.py → Q8_0
#   2. quant    : llama-quantize → Q4_K_M (same quantization as R30/R31/R33)
#   3. ollama   : create vaca-r34:latest from the Q4 GGUF (bare-prompt template,
#                 same as vaca-r31/r33 — the model the retention eval will use)
#   4. done     : write round34b-deploy.done marker + summary
# Log: training/cloud/round34b-deploy.log (tail -f from anywhere)
#
# Usage (ON THE AGENT, detached — survives SSH drops):
#   setsid bash scripts/auto-deploy-r34.sh > training/cloud/round34b-deploy.log 2>&1 < /dev/null &
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root on the agent

MERGE_VENV="/home/llmlab/vaca-train-venv/bin/python"   # the venv that trained R34b
ROUND34B="training/cloud/out/round34b"
MERGED="$ROUND34B/merged"
GGUF_DIR="$ROUND34B/gguf"
GGUF_Q8="$GGUF_DIR/vaca-r34.Q8_0.gguf"
GGUF_Q4="$GGUF_DIR/vaca-r34.Q4_K_M.gguf"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
QUANT="$HOME/.unsloth/llama.cpp/llama-quantize"
OLLAMA_NAME="vaca-r34"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { say "❌ $*"; exit 1; }

say "=== R34 deploy started $(date) ==="
[ -d "$MERGED" ] || fail "merged fp16 not found at $MERGED — run build-r34b-merged.py first"
df -h / | tail -1

# ── 1+2. convert + quantize (~20 min) ───────────────────────────────────────
mkdir -p "$GGUF_DIR"
say "── [1/3] convert merged fp16 → Q8_0 (~10-15 min) ──"
"$MERGE_VENV" "$CONVERT" "$MERGED" --outfile "$GGUF_Q8" --outtype q8_0 || fail "convert failed"
say "── [2/3] quantize Q8_0 → Q4_K_M (~5 min) ──"
"$QUANT" --allow-requantize "$GGUF_Q8" "$GGUF_Q4" q4_k_m || fail "quantize failed"
Q4_SIZE="$(stat -c %s "$GGUF_Q4")"
[ "$Q4_SIZE" -gt 8000000000 ] || fail "Q4 GGUF only ${Q4_SIZE} bytes — refusing to deploy partial export"
say "✅ Q4_K_M GGUF: $(du -h "$GGUF_Q4" | cut -f1)"

# ── 3. ollama create (bare {{ .Prompt }} template — matches vaca-r31/r33) ──
say "── [3/3] ollama create $OLLAMA_NAME ──"
cat > "$GGUF_DIR/Modelfile" <<EOF
FROM $GGUF_Q4
TEMPLATE {{ .Prompt }}
EOF
ollama create vaca-r34 -f "$GGUF_DIR/Modelfile" || fail "ollama create failed"
ollama list | grep vaca-r34 || fail "vaca-r34 not in ollama list"

# ── cleanup + done marker ───────────────────────────────────────────────────
say "── cleanup (keep Q4 GGUF + merged fp16; drop Q8 intermediate) ──"
rm -f "$GGUF_Q8"
say "  removed Q8 intermediate"
df -h / | tail -1

say "✅✅ R34 DEPLOY COMPLETE — $(date)"
echo "DEPLOY_DONE at $(date)" > "$ROUND34B/round34b-deploy.done"
say "  ollama model: $(ollama list | grep vaca-r34)"