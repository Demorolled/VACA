#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-10 merged safetensors -> q4_k_m GGUF, deploy to dspark,
# then drop the old R9 model that is superseded.
# =============================================================================
# Prereq:  python3 scripts/download-round10-merged.py   (adapter + merged/)
#
# Steps:
#   1. convert_hf_to_gguf.py (unsloth llama.cpp)  -> R10.F16.gguf
#   2. llama-quantize q4_k_m                       -> R10.Q4_K_M.gguf
#   3. copy to models/, point dspark at it, restart (tmux:dspark)
#   4. health-check + smoke generation
#   5. delete the OLD R9 GGUF from models/ (superseded by R10)
#
# The round-10 adapter is kept for chaining; the F16 intermediate is removed
# after quantization to save ~15 GB.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND10="$CLOUD/out/round10"
MERGED="$ROUND10/merged"
ADAPTER="$ROUND10/adapter"
MODELS="$PROJECT_ROOT/models"

NAME="Qwen2.5-7B-Instruct-Uncensored"
F16="$ROUND10/$NAME.R10.F16.gguf"
Q4="$ROUND10/$NAME.R10.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R10.Q4_K_M.gguf"
OLD_R9="$MODELS/$NAME.R9.Q4_K_M.gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-10 deploy ==="
[ -f "$MERGED/model.safetensors.index.json" ] || { echo "❌ No merged model — run download-round10-merged.py first" >&2; exit 1; }
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 1. Convert (HF -> F16 GGUF) ───────────────────────────────────────────
# Safeguard: save_pretrained_merged may not write tokenizer files into the
# merged dir — copy them from the adapter if missing (convert needs them).
for tf in tokenizer.json tokenizer_config.json chat_template.jinja README.md; do
  if [ ! -f "$MERGED/$tf" ] && [ -f "$ADAPTER/$tf" ]; then
    cp "$ADAPTER/$tf" "$MERGED/$tf"
    echo "   (copied missing $tf from adapter -> merged)"
  fi
done

echo "--- [1/5] convert_hf_to_gguf (merged -> F16 GGUF) ---"
python3 "$CONVERT" "$MERGED" --outfile "$F16" --outtype f16 2>&1 | tail -6

# ─── 2. Quantize (F16 -> q4_k_m) ───────────────────────────────────────────
echo "--- [2/5] llama-quantize q4_k_m ---"
"$QUANTIZE" "$F16" "$Q4" q4_k_m 8 2>&1 | tail -6
rm -f "$F16"
echo "   ✓ $Q4"

# ─── 3. Deploy ─────────────────────────────────────────────────────────────
echo "--- [3/5] deploy to dspark (tmux:dspark restart) ---"
cp "$Q4" "$DEPLOY_Q4"
echo "DSPARK_TARGET=$DEPLOY_Q4" > "$PROJECT_ROOT/scripts/dspark-target.env"

tmux kill-session -t dspark 2>/dev/null || true
tmux new-session -d -s dspark \
  "python3 $PROJECT_ROOT/scripts/dspark_server.py --target $DEPLOY_Q4 --draft qwen2.5-coder:0.5b --port 8000 --n-ctx 16384 --n-gpu-layers -1 --draft-mode none > $PROJECT_ROOT/scripts/dspark.log 2>&1"
echo "   dspark restarting in tmux:dspark — waiting 60s for load..."
sleep 60

# ─── 4. Health check (retry loop — dspark warm-up is variable) + smoke ─────
echo "--- [4/5] health check (retrying up to 5×30s) ---"
HEALTH_OK=0
for attempt in 1 2 3 4 5; do
  sleep 30
  HEALTH="$(curl -s -m 10 http://127.0.0.1:8000/v1/health 2>&1 || true)"
  echo "   attempt $attempt: ${HEALTH:0:80}"
  if echo "$HEALTH" | grep -q '"status":"ok"\|"status": "ok"'; then
    HEALTH_OK=1
    break
  fi
done
[ "$HEALTH_OK" = "1" ] || { echo "⚠️  health not OK after 5 tries — inspect scripts/dspark.log" >&2; exit 1; }

echo "   Smoke generation test (may take ~90s)..."
curl -s -m 150 http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"x","messages":[{"role":"user","content":"Create a clean login form. Reply with OK only."}],"max_tokens":24,"stream":false}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   ✓', d['choices'][0]['message']['content'][:60].replace(chr(10),' '))" 2>&1 | head -2

# ─── 5. Drop the superseded R9 ─────────────────────────────────────────────
echo "--- [5/5] removing superseded R9 model copy ---"
rm -f "$OLD_R9"
echo "   ✓ deleted: $OLD_R9"

echo ""
echo "✅ Round-10 model deployed. dspark now serves R10 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
echo "   Old R9 GGUF removed from models/. (stock + R6 GGUFs untouched)"
