#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build-gemma4-gguf.sh — convert the fp16 Gemma 4 12B -> q4_k_m GGUF.
# =============================================================================
#   source: ~/Desktop/gemma4/          (model.safetensors fp16, the HF bucket)
#   step 1: convert_hf_to_gguf.py      fp16 -> GGUF f16  (~24G, the big one)
#   step 2: llama-quantize             f16  -> q4_k_m   (~8G final)
#   output: visual-ai-architect/models/gemma4-12b-q4_k_m.gguf
#
# Uses the llama.cpp toolchain bundled by unsloth (has GEMMA4 arch support).
# Run ON THE AGENT:
#   bash scripts/build-gemma4-gguf.sh
#   GGUF_QUANT=q8_0 bash scripts/build-gemma4-gguf.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

GGUF_QUANT="${GGUF_QUANT:-q4_k_m}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${SRC:-$HOME/Desktop/gemma4}"
LC="$HOME/.unsloth/llama.cpp"
OUTDIR="$ROOT/models"
mkdir -p "$OUTDIR"

F16_OUT="$OUTDIR/gemma4-12b-f16.gguf"
Q_OUT="$OUTDIR/gemma4-12b-${GGUF_QUANT}.gguf"

[ -f "$SRC/model.safetensors" ] || { echo "❌ no model.safetensors in $SRC" >&2; exit 1; }
[ -f "$LC/convert_hf_to_gguf.py" ] || { echo "❌ missing $LC/convert_hf_to_gguf.py" >&2; exit 1; }
[ -x "$LC/build/bin/llama-quantize" ] || { echo "❌ missing llama-quantize" >&2; exit 1; }

echo "─── Step 1/2: fp16 -> GGUF (f16) ───"
/usr/bin/python3 "$LC/convert_hf_to_gguf.py" "$SRC" \
  --outfile "$F16_OUT" \
  --outtype f16 || { echo "❌ convert failed" >&2; exit 1; }
echo "✅ f16 GGUF: $(ls -la "$F16_OUT" | awk '{print $5}') bytes"

echo "─── Step 2/2: quantize -> $GGUF_QUANT ───"
"$LC/build/bin/llama-quantize" "$F16_OUT" "$Q_OUT" "$GGUF_QUANT" || { echo "❌ quantize failed" >&2; exit 1; }
echo "✅ q4 GGUF: $(ls -la "$Q_OUT" | awk '{print $5}') bytes"

echo "─── cleanup f16 intermediate ───"
rm -f "$F16_OUT"
echo "✅ Done: $Q_OUT"
du -sh "$Q_OUT"