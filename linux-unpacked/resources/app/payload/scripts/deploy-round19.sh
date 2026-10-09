#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-19 merged 14B safetensors -> q4_k_m GGUF and deploy to
# dspark. This REPLACES the current R18 Q4 model — the live R18 GGUF is backed
# up to model-backups/ first (guarded).
# =============================================================================
# Prereq:  scripts/build-r19-merged.py
#          (training/cloud/out/round19/merged/ = real fp16 merged)
#
# Quant: q4_k_m chosen to MATCH the current live profile — the R17 Q4 was
#        measured ~18.7 tok/s on this hardware and the user picked Q4 for
#        speed. 14B Q4 ≈ 8.99GB, fits 2x RTX 3060.
#
# Path: Q8_0 directly from HF (convert supports it), then requantize
#        Q8 -> Q4_K_M with --allow-requantize (the proven R17/R18 path) —
#        peak ≈ 44G, fits the disk.
#
# Steps:
#   1. convert_hf_to_gguf.py  -> R19.Q8_0.gguf (direct, no F16 intermediate)
#   2. llama-quantize q4_k_m  -> R19.Q4_K_M.gguf (from Q8, --allow-requantize)
#   3. back up the R18 Q4 GGUF to model-backups/
#   4. copy to models/, point dspark at it, restart (tmux:dspark)
#   5. health-check + smoke generation
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND19="$CLOUD/out/round19"
MERGED="$ROUND19/merged"
ADAPTER="$ROUND19/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-Coder-14B-Instruct-Uncensored"
Q8="$ROUND19/$NAME.R19.Q8_0.gguf"
Q4="$ROUND19/$NAME.R19.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R19.Q4_K_M.gguf"
OLD_R18="$MODELS/$NAME.R18.Q4_K_M.gguf"
BACKUP_R18="$BACKUP_DIR/$NAME.R18.Q4_K_M.$(date +%Y-%m-%d).gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-19 deploy (14B coder R19 replaces R18) ==="
if [ ! -f "$MERGED/model.safetensors.index.json" ] && [ ! -f "$MERGED/model.safetensors" ]; then
  echo "❌ No merged model — run build-r19-merged.py first" >&2
  exit 1
fi
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R18 Q4 backup must exist before we drop it ───────────
if [ "${KEEP_R18:-0}" != "1" ]; then
  if [ ! -f "$BACKUP_R18" ] && [ -f "$OLD_R18" ]; then
    echo "--- [0/5] backing up the live R18 Q4 GGUF ---"
    cp -n "$OLD_R18" "$BACKUP_R18"
    echo "   ✓ backed up: $BACKUP_R18"
  elif [ ! -f "$BACKUP_R18" ]; then
    echo "⚠️  R18 Q4 not found at $OLD_R18 and no backup." >&2
    [ "${SKIP_R18_GUARD:-0}" = "1" ] || exit 1
  else
    echo "   ✓ R18 backup already present: $BACKUP_R18"
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

echo "--- [1/5] convert_hf_to_gguf (merged 14B -> Q8_0 GGUF, no F16 intermediate) ---"
python3 "$CONVERT" "$MERGED" --outfile "$Q8" --outtype q8_0 2>&1 | tail -6

echo "--- [2/5] llama-quantize q4_k_m (requantize from Q8, proven R17 path) ---"
# NOTE: llama.cpp's arg parser only reads flags while args start with '--', so
# --allow-requantize MUST come BEFORE the positional args or it is silently ignored.
"$QUANTIZE" --allow-requantize "$Q8" "$Q4" q4_k_m 8 2>&1 | tail -6
echo "   ✓ $Q4"

echo "--- [3/5] deploy to dspark (tmux:dspark restart) ---"
cp "$Q4" "$DEPLOY_Q4"
echo "DSPARK_TARGET=$DEPLOY_Q4" > "$PROJECT_ROOT/scripts/dspark-target.env"

tmux kill-session -t dspark 2>/dev/null || true
tmux new-session -d -s dspark \
  "python3 $PROJECT_ROOT/scripts/dspark_server.py --target $DEPLOY_Q4 --draft qwen2.5-coder:0.5b --port 8000 --n-ctx 16384 --n-gpu-layers -1 --draft-mode none --model-id qwen2.5-coder-14b-uncensored-dspark > $PROJECT_ROOT/scripts/dspark.log 2>&1"
echo "   dspark restarting — waiting 90s for load (14B Q4 ~1-2 min)..."
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

# ─── 5b. Push the trained adapter to Kaggle (next round's resume point) ──
# The R18 adapter was NEVER pushed after its own deploy — R19's kernel silently
# depended on it existing, and the auto-push had to discover + upload it at the
# last minute (T3b: deploy scripts now own this, so every future round has its
# chained-resume point the moment it exists). Flat zip, like the R18 push.
echo "--- [5b] pushing adapter to Kaggle (vaca-r19-adapter) ---"
ADAPTER_SLUG="vaca-r19-adapter"
if [ "${PUSH_ADAPTER:-1}" = "0" ]; then
  echo "   PUSH_ADAPTER=0 — skipping adapter push."
elif timeout 60 kaggle datasets status "stevenawoods/$ADAPTER_SLUG" >/dev/null 2>&1; then
  echo "   ✓ $ADAPTER_SLUG already on Kaggle — skipping."
elif [ -d "$ADAPTER" ] && [ -f "$ADAPTER/adapter_config.json" ]; then
  ADZIP="$(mktemp -d)"
  (cd "$ADAPTER" && zip -qr "$ADZIP/adapter.zip" .)
  cat > "$ADZIP/dataset-metadata.json" <<EOF
{
  "id": "stevenawoods/$ADAPTER_SLUG",
  "title": "VACA R19 QLoRA adapter (14B coder)",
  "subtitle": "R19 trained LoRA — chained resume for Round-20",
  "licenses": [{ "name": "other" }]
}
EOF
  timeout 240 kaggle datasets create -p "$ADZIP" 2>&1 | tail -3
  rm -rf "$ADZIP"
  echo "   ✓ adapter pushed to Kaggle as stevenawoods/$ADAPTER_SLUG"
else
  echo "   ⚠️  adapter not found at $ADAPTER — skipping push (chain resume for R20 will need it)"
fi

# ─── 5. Drop the superseded R18 Q4 (unless KEEP_R18=1) ─────────────────────
if [ "${KEEP_R18:-0}" = "1" ]; then
  echo "--- [5/5] KEEP_R18=1 — keeping the R18 Q4 in models/ ---"
elif [ -f "$OLD_R18" ]; then
  echo "--- [5/5] removing superseded R18 Q4 ---"
  rm -f "$OLD_R18"
  echo "   ✓ deleted: $OLD_R18"
  echo "   (backup preserved at: $BACKUP_R18)"
else
  echo "   (no R18 copy to delete)"
fi

echo ""
echo "✅ Round-19 (14B coder) deployed. dspark now serves R19 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
