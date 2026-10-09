#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto-deploy-r36.sh — deploy the UNIFIED model (r33 base + r34b + r35 + r36)
# =============================================================================
# Eval battery passed: R35 comp 98.6%, R36 comp 97.5%, entry-point 19/19 (100%).
# The merged fp16 lives at training/cloud/out/unified/merged (built by
# build-r37-merged.py). This script finishes the proven chain:
#   1. convert : llama.cpp convert_hf_to_gguf.py → Q8_0 (15.7 GB, best quality,
#                same as vaca-r34 — the user chose Q8 over Q4)
#   2. ollama  : create vaca-r36:latest from the Q8 GGUF (bare-prompt template,
#                matches vaca-r31/r33/r34)
#   3. done    : write unified-deploy.done marker + summary
# Log: training/cloud/out/unified/deploy.log
#
# Usage (ON THE AGENT, detached — survives SSH drops):
#   setsid bash scripts/auto-deploy-r36.sh > training/cloud/out/unified/deploy.log 2>&1 < /dev/null &
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root on the agent

MERGE_VENV="/home/llmlab/vaca-train-venv/bin/python"
UNIFIED="training/cloud/out/unified"
MERGED="$UNIFIED/merged"
GGUF_DIR="$UNIFIED/gguf"
GGUF_Q8="$GGUF_DIR/vaca-r36.Q8_0.gguf"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
OLLAMA_NAME="vaca-r36"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { say "❌ $*"; exit 1; }

say "=== R36 deploy started $(date) ==="
[ -d "$MERGED" ] || fail "merged fp16 not found at $MERGED — run build-r37-merged.py first"
df -h / | tail -1

# ── 1. convert → Q8_0 (~10-15 min) ─────────────────────────────────────────
mkdir -p "$GGUF_DIR"
say "── [1/2] convert merged fp16 → Q8_0 (~10-15 min) ──"
"$MERGE_VENV" "$CONVERT" "$MERGED" --outfile "$GGUF_Q8" --outtype q8_0 || fail "convert failed"
Q8_SIZE="$(stat -c %s "$GGUF_Q8")"
[ "$Q8_SIZE" -gt 13000000000 ] || fail "Q8 GGUF only ${Q8_SIZE} bytes — refusing partial export"
say "✅ Q8_0 GGUF: $(du -h "$GGUF_Q8" | cut -f1)"

# ── 2. ollama create (bare {{ .Prompt }} template — matches vaca-r31/r33/r34) ──
say "── [2/2] ollama create $OLLAMA_NAME ──"
cat > "$GGUF_DIR/Modelfile" <<EOF
FROM $GGUF_Q8
TEMPLATE {{ .Prompt }}
EOF
ollama create vaca-r36 -f "$GGUF_DIR/Modelfile" || fail "ollama create failed"
ollama list | grep vaca-r36 || fail "vaca-r36 not in ollama list"

say "── cleanup (keep merged fp16 + Q8 GGUF) ──"
df -h / | tail -1

say "✅✅ R36 DEPLOY COMPLETE — $(date)"
echo "DEPLOY_DONE at $(date)" > "$UNIFIED/unified-deploy.done"
say "  ollama model: $(ollama list | grep vaca-r36)"