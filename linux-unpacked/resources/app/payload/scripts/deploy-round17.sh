#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-17 merged 14B safetensors -> q8_0 GGUF and deploy to
# dspark. This REPLACES the 7B R16 model — the current R16 GGUF is backed up
# to model-backups/ first (guarded).
# =============================================================================
# Prereq:  scripts/download-round17-merged.py + scripts/build-r17-merged.py
#          (out/round17/merged/  = real fp16 merged)
#
# Quant: q8_0 (8-bit, near-lossless vs F16) chosen over q4_k_m for quality.
#        Size ~14.9GB — fits 2x RTX 3060 (24GB) with ~9GB KV-cache headroom.
#
# Steps:
#   1. convert_hf_to_gguf.py  -> R17.F16.gguf
#   2. llama-quantize q8_0    -> R17.Q8_0.gguf
#   3. back up the R16 7B GGUF to model-backups/
#   4. copy to models/, point dspark at it, restart (tmux:dspark)
#   5. health-check + smoke generation
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND17="$CLOUD/out/round17"
MERGED="$ROUND17/merged"
ADAPTER="$ROUND17/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-Coder-14B-Instruct-Uncensored"
F16="$ROUND17/$NAME.R17.F16.gguf"
Q8="$ROUND17/$NAME.R17.Q8_0.gguf"
DEPLOY_Q8="$MODELS/$NAME.R17.Q8_0.gguf"
OLD_R16="$MODELS/Qwen2.5-7B-Instruct-Uncensored.R16.Q4_K_M.gguf"
BACKUP_R16="$BACKUP_DIR/Qwen2.5-7B-Instruct-Uncensored.R16.Q4_K_M.$(date +%Y-%m-%d).gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-17 deploy (14B coder replaces 7B R16) ==="
if [ ! -f "$MERGED/model.safetensors.index.json" ] && [ ! -f "$MERGED/model.safetensors" ]; then
  echo "❌ No merged model — run download-round17-merged.py + build-r17-merged.py first" >&2
  exit 1
fi
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R16 7B backup must exist before we drop it ───────────
if [ "${KEEP_R16:-0}" != "1" ]; then
  if [ ! -f "$BACKUP_R16" ] && [ -f "$OLD_R16" ]; then
    echo "--- [0/5] backing up the live 7B R16 GGUF ---"
    cp -n "$OLD_R16" "$BACKUP_R16"
    echo "   ✓ backed up: $BACKUP_R16"
  elif [ ! -f "$BACKUP_R16" ]; then
    echo "⚠️  R16 7B not found at $OLD_R16 and no backup." >&2
    [ "${SKIP_R16_GUARD:-0}" = "1" ] || exit 1
  else
    echo "   ✓ R16 backup already present: $BACKUP_R16"
  fi
fi

# ─── 1. Tokenizer files may live only in the adapter dir ───────────────────
for tf in tokenizer.json tokenizer_config.json chat_template.jinja README.md; do
  if [ ! -f "$MERGED/$tf" ] && [ -f "$ADAPTER/$tf" ]; then
    cp "$ADAPTER/$tf" "$MERGED/$tf"
  fi
done

# ─── 1b. Strip stale QLoRA quant metadata ─────────────────────────────
python3 - "$MERGED/config.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
if "quantization_config" in d:
    del d["quantization_config"]
    json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
    print("   (stripped stale quantization_config)")
PY

echo "--- [1/5] convert_hf_to_gguf (merged 14B -> F16 GGUF) ---"
python3 "$CONVERT" "$MERGED" --outfile "$F16" --outtype f16 2>&1 | tail -6

echo "--- [2/5] llama-quantize q8_0 ---"
"$QUANTIZE" "$F16" "$Q8" q8_0 8 2>&1 | tail -6
rm -f "$F16"
echo "   ✓ $Q8"

echo "--- [3/5] deploy to dspark (tmux:dspark restart) ---"
cp "$Q8" "$DEPLOY_Q8"
echo "DSPARK_TARGET=$DEPLOY_Q8" > "$PROJECT_ROOT/scripts/dspark-target.env"

tmux kill-session -t dspark 2>/dev/null || true
tmux new-session -d -s dspark \
  "python3 $PROJECT_ROOT/scripts/dspark_server.py --target $DEPLOY_Q8 --draft qwen2.5-coder:0.5b --port 8000 --n-ctx 16384 --n-gpu-layers -1 --draft-mode none --model-id qwen2.5-coder-14b-uncensored-dspark > $PROJECT_ROOT/scripts/dspark.log 2>&1"
echo "   dspark restarting — waiting 90s for load (14B is ~2x the 7B)..."
sleep 90

echo "--- [4/5] health check (retrying up to 5×30s) ---"
HEALTH_OK=0
for attempt in 1 2 3 4 5; do
  sleep 30
  HEALTH="$(curl -s -m 10 http://127.0.0.1:8000/v1/health 2>&1 || true)"
  if echo "$HEALTH" | grep -q '"status":"ok"'; then
    HEALTH_OK=1
    echo "   attempt $attempt: OK"
    break
  fi
  echo "   attempt $attempt: not ready yet"
done
if [ "$HEALTH_OK" != "1" ]; then
  echo "   ❌ dspark health never OK. tail -40 $PROJECT_ROOT/scripts/dspark.log" >&2
  exit 1
fi

echo "   Smoke generation test (may take ~2 min)..."
SMOKE="$(curl -s -m 180 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"x","messages":[{"role":"user","content":"Reply with the single word: OK"}],"max_tokens":10}' 2>&1 || true)"
if echo "$SMOKE" | grep -q '"content"'; then
  echo "   ✓ OK"
else
  echo "   ⚠️  smoke response unexpected: ${SMOKE:0:120}"
fi

# ─── 5. Drop the superseded R16 7B (unless KEEP_R16=1) ─────────────────────
if [ "${KEEP_R16:-0}" = "1" ]; then
  echo "--- [5/5] KEEP_R16=1 — keeping the 7B R16 in models/ ---"
elif [ -f "$OLD_R16" ]; then
  echo "--- [5/5] removing superseded 7B R16 ---"
  rm -f "$OLD_R16"
  echo "   ✓ deleted: $OLD_R16"
  echo "   (backup preserved at: $BACKUP_R16)"
else
  echo "   (no R16 copy to delete)"
fi

echo ""
echo "✅ Round-17 (14B coder) deployed. dspark now serves R17 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
