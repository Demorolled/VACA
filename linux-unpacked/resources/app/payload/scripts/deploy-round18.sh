#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-18 merged 14B safetensors -> q4_k_m GGUF and deploy to
# dspark. This REPLACES the current R17 Q4 model — the live R17 GGUF is backed
# up to model-backups/ first (guarded).
# =============================================================================
# Prereq:  scripts/build-r18-merged.py
#          (training/cloud/out/round18/merged/ = real fp16 merged)
#
# Quant: q4_k_m chosen to MATCH the current live profile — the R17 Q4 was
#        measured ~18.7 tok/s on this hardware and the user picked Q4 for
#        speed (q8_0 measured far slower). 14B Q4 ≈ 8.99GB, fits 2x RTX 3060.
#
# Disk note (2026-08-16): the F16-intermediate path (merged 28G + F16 29G +
#        Q4 9G ≈ 67G peak) exceeded the ~55G free on this machine and the
#        earlier run died mid-convert on a machine reboot. Converted to
#        Q8_0 directly (convert supports it), then requantized Q8 -> Q4_K_M
#        with --allow-requantize (the proven R17 path) — peak ≈ 44G.
#
# Steps:
#   1. convert_hf_to_gguf.py  -> R18.Q8_0.gguf (direct, no F16 intermediate)
#   2. llama-quantize q4_k_m  -> R18.Q4_K_M.gguf (from Q8, --allow-requantize)
#   3. back up the R17 Q4 GGUF to model-backups/
#   4. copy to models/, point dspark at it, restart (tmux:dspark)
#   5. health-check + smoke generation
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND18="$CLOUD/out/round18"
MERGED="$ROUND18/merged"
ADAPTER="$ROUND18/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-Coder-14B-Instruct-Uncensored"
Q8="$ROUND18/$NAME.R18.Q8_0.gguf"
Q4="$ROUND18/$NAME.R18.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R18.Q4_K_M.gguf"
OLD_R17="$MODELS/$NAME.R17.Q4_K_M.gguf"
BACKUP_R17="$BACKUP_DIR/$NAME.R17.Q4_K_M.$(date +%Y-%m-%d).gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-18 deploy (14B coder R18 replaces R17) ==="
if [ ! -f "$MERGED/model.safetensors.index.json" ] && [ ! -f "$MERGED/model.safetensors" ]; then
  echo "❌ No merged model — run build-r18-merged.py first" >&2
  exit 1
fi
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R17 Q4 backup must exist before we drop it ───────────
if [ "${KEEP_R17:-0}" != "1" ]; then
  if [ ! -f "$BACKUP_R17" ] && [ -f "$OLD_R17" ]; then
    echo "--- [0/5] backing up the live R17 Q4 GGUF ---"
    cp -n "$OLD_R17" "$BACKUP_R17"
    echo "   ✓ backed up: $BACKUP_R17"
  elif [ ! -f "$BACKUP_R17" ]; then
    echo "⚠️  R17 Q4 not found at $OLD_R17 and no backup." >&2
    [ "${SKIP_R17_GUARD:-0}" = "1" ] || exit 1
  else
    echo "   ✓ R17 backup already present: $BACKUP_R17"
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

# ─── 5. Drop the superseded R17 Q4 (unless KEEP_R17=1) ─────────────────────
if [ "${KEEP_R17:-0}" = "1" ]; then
  echo "--- [5/5] KEEP_R17=1 — keeping the R17 Q4 in models/ ---"
elif [ -f "$OLD_R17" ]; then
  echo "--- [5/5] removing superseded R17 Q4 ---"
  rm -f "$OLD_R17"
  echo "   ✓ deleted: $OLD_R17"
  echo "   (backup preserved at: $BACKUP_R17)"
else
  echo "   (no R17 copy to delete)"
fi

echo ""
echo "✅ Round-18 (14B coder) deployed. dspark now serves R18 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
