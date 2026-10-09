#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# quantize-r40-q4.sh — build vaca-r40-q4 (Q4_K_M) alongside vaca-r40 (Q8_0)
# =============================================================================
# Why: measured single-stream throughput on 3x RTX 3060 is 21.6 tok/s for the
# 15 GB Q8_0 policy and 34.7 tok/s for a 9 GB Q4 14B — 1.6x. Since Ollama
# serialises concurrent requests on this box (0.96x, see ornith-trainer's
# scripts/bench_concurrency.py), token rate is the only throughput lever the
# collection loop has, and quant is where it lives.
#
# Path: quantize from the fp16 MERGED weights, not from the deployed Q8_0 blob.
# llama-quantize can requantize a quantized source with --allow-requantize but
# warns it "can severely reduce quality"; r40-merged is already on disk, so the
# clean two-step (fp16 GGUF -> Q4_K_M) costs ~20 min more and no quality.
#
# Usage (ON THE AGENT, detached — survives SSH drops):
#   tmux new-session -d -s q4 "bash scripts/quantize-r40-q4.sh > /tmp/quant-r40-q4.log 2>&1"
# Log: /tmp/quant-r40-q4.log
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root on the agent

VENV="/home/llmlab/vaca-train-venv/bin/python"
UNIFIED="training/cloud/out/unified"
MERGED="$UNIFIED/r40-merged"
OUT="$UNIFIED/gguf-r40-q4"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
QUANTIZE="/usr/local/lib/ollama/llama-quantize"
F16="$OUT/vaca-r40.f16.gguf"
Q4="$OUT/vaca-r40.Q4_K_M.gguf"
OLLAMA_NAME="vaca-r40-q4"

say()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { say "❌ $*"; exit 1; }

say "=== R40 Q4_K_M build started $(date) ==="
[ -d "$MERGED" ] || fail "merged fp16 not found at $MERGED"
[ -x "$VENV" ]   || fail "venv python not found at $VENV"
# NOTE: -f, not -x. This is a .py invoked as "$VENV $CONVERT", so the executable
# bit is irrelevant — requiring it (as this script first did) fails on a file
# that is present and perfectly usable.
[ -f "$CONVERT" ] || fail "convert_hf_to_gguf.py not found at $CONVERT"
[ -x "$QUANTIZE" ] || fail "llama-quantize not found at $QUANTIZE"
df -h / | tail -1
mkdir -p "$OUT"

# ── 1. merged fp16 -> f16 GGUF ───────────────────────────────────────────────
if [ -s "$F16" ]; then
  say "── [1/3] f16 GGUF already present, skipping convert"
else
  say "── [1/3] convert merged fp16 -> f16 GGUF (~15-25 min) ──"
  "$VENV" "$CONVERT" "$MERGED" --outfile "$F16" --outtype f16 || fail "convert failed"
fi
F16_SIZE="$(stat -c %s "$F16" 2>/dev/null || echo 0)"
[ "$F16_SIZE" -gt 25000000000 ] || fail "f16 GGUF only ${F16_SIZE} bytes — refusing partial export"
say "✅ f16 GGUF: $(du -h "$F16" | cut -f1)"
df -h / | tail -1

# ── 2. f16 GGUF -> Q4_K_M ────────────────────────────────────────────────────
if [ -s "$Q4" ]; then
  say "── [2/3] Q4_K_M already present, skipping quantize"
else
  say "── [2/3] quantize f16 -> Q4_K_M (~5-10 min) ──"
  "$QUANTIZE" "$F16" "$Q4" Q4_K_M || fail "quantize failed"
fi
Q4_SIZE="$(stat -c %s "$Q4" 2>/dev/null || echo 0)"
# Q4_K_M of a 14.8B model is ~9-10 GB. A much smaller file means a truncated run.
[ "$Q4_SIZE" -gt 8000000000 ] || fail "Q4_K_M only ${Q4_SIZE} bytes — refusing partial export"
say "✅ Q4_K_M GGUF: $(du -h "$Q4" | cut -f1)"

# ── 3. ollama create, preserving r40's TEMPLATE exactly ──────────────────────
# The template is NOT cosmetic: vaca-r40 ships `TEMPLATE {{ .Prompt }}` (a bare
# prompt), matching vaca-r31/r33/r34/r36/r38. Reuse whatever the deployed model
# actually has rather than re-declaring it, so the Q4 copy cannot silently drift
# into a chat-formatted prompt the fine-tune was never trained on.
say "── [3/3] ollama create $OLLAMA_NAME ──"
TEMPLATE="$(ollama show --modelfile vaca-r40:latest 2>/dev/null | grep '^TEMPLATE ' || true)"
[ -n "$TEMPLATE" ] || fail "could not read TEMPLATE from vaca-r40 — refusing to guess"
say "  reusing: $TEMPLATE"
# FROM must be an ABSOLUTE path. With a relative one, Ollama does not resolve it
# against the Modelfile or the cwd — it parses it as a model REFERENCE and fails
# with a bare "400 Bad Request: invalid model name", which reads like a bad
# target name rather than a bad FROM. (The shipped r40 deploy script got away
# with a relative path; this Ollama build does not.)
Q4_ABS="$(cd "$(dirname "$Q4")" && pwd)/$(basename "$Q4")"
printf 'FROM %s\n%s\n' "$Q4_ABS" "$TEMPLATE" > "$OUT/Modelfile"
ollama create "$OLLAMA_NAME" -f "$OUT/Modelfile" || fail "ollama create failed"
ollama list | grep -E "^${OLLAMA_NAME}" || fail "$OLLAMA_NAME not in ollama list"

# ── cleanup: the f16 GGUF is regenerable from r40-merged, keep only Q4 ───────
say "── cleanup: dropping f16 GGUF (regenerable from $MERGED) ──"
rm -f "$F16"
df -h / | tail -1

say "✅✅ R40 Q4_K_M READY — $(date)"
say "  ollama model: $(ollama list | grep -E "^${OLLAMA_NAME}")"
say "  benchmark it: python3 ~/ornith-trainer/scripts/bench_concurrency.py --model $OLLAMA_NAME --n 2"
echo "QUANT_DONE at $(date)" > "$UNIFIED/r40-q4.done"
