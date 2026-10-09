#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto-deploy-r40.sh — deploy r40-merged (unified base + ΔR40) as vaca-r40
# =============================================================================
# R40 final adapter merged into the unified base by build-r40-merged.py →
# out/unified/r40-merged (fp16). Same proven chain as r38:
#   1. convert : llama.cpp convert_hf_to_gguf.py → Q8_0 (~15.7 GB)
#   2. ollama  : create vaca-r40:latest from the Q8 GGUF (bare-prompt template,
#                matches vaca-r31/r33/r34/r36/r38)
#   3. done    : marker + summary
# Log: training/cloud/out/unified/deploy-r40.log
#
# Usage (ON THE AGENT, detached — survives SSH drops):
#   setsid bash scripts/auto-deploy-r40.sh > training/cloud/out/unified/deploy-r40.log 2>&1 < /dev/null &
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root on the agent

MERGE_VENV="/home/llmlab/vaca-train-venv/bin/python"
UNIFIED="training/cloud/out/unified"
MERGED="$UNIFIED/r40-merged"
GGUF_DIR="$UNIFIED/gguf"
GGUF_Q8="$GGUF_DIR/vaca-r40.Q8_0.gguf"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
OLLAMA_NAME="vaca-r40"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { say "❌ $*"; exit 1; }

say "=== R40 deploy started $(date) ==="
[ -d "$MERGED" ] || fail "merged fp16 not found at $MERGED — run build-r40-merged.py first"
df -h / | tail -1

# ── 1. convert → Q8_0 (~10-15 min) ─────────────────────────────────────────
mkdir -p "$GGUF_DIR"
say "── [1/2] convert merged fp16 → Q8_0 (~10-15 min) ──"
"$MERGE_VENV" "$CONVERT" "$MERGED" --outfile "$GGUF_Q8" --outtype q8_0 || fail "convert failed"
Q8_SIZE="$(stat -c %s "$GGUF_Q8")"
[ "$Q8_SIZE" -gt 13000000000 ] || fail "Q8 GGUF only ${Q8_SIZE} bytes — refusing partial export"
say "✅ Q8_0 GGUF: $(du -h "$GGUF_Q8" | cut -f1)"

# ── 2. ollama create (bare {{ .Prompt }} template — matches vaca-r31/r33/r34/r36/r38) ──
say "── [2/2] ollama create $OLLAMA_NAME ──"
cat > "$GGUF_DIR/Modelfile" <<EOF
FROM $GGUF_Q8
TEMPLATE {{ .Prompt }}
EOF
ollama create vaca-r40 -f "$GGUF_DIR/Modelfile" || fail "ollama create failed"
ollama list | grep vaca-r40 || fail "vaca-r40 not in ollama list"

say "── cleanup (keep merged fp16 + Q8 GGUF) ──"
df -h / | tail -1

say "✅✅ R40 DEPLOY COMPLETE — $(date)"
echo "DEPLOY_DONE at $(date)" > "$UNIFIED/r40-deploy.done"
say "  ollama model: $(ollama list | grep vaca-r40)"