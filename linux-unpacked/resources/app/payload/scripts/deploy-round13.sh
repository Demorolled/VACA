#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-13 merged safetensors -> q4_k_m GGUF, deploy to dspark,
# then drop the old R12 model that is superseded.
# =============================================================================
# Prereq:  fetch the round-13 kernel output into training/cloud/out/round13/:
#          out/round13/adapter/   (adapter_round13 — LoRA for future chaining)
#          out/round13/merged/    (merged 16-bit safetensors + config/tokenizer)
#
# Steps:
#   1. convert_hf_to_gguf.py (unsloth llama.cpp)  -> R13.F16.gguf
#   2. llama-quantize q4_k_m                       -> R13.Q4_K_M.gguf
#   3. copy to models/, point dspark at it, restart (tmux:dspark)
#   4. health-check + smoke generation
#   5. BACK UP the old R12 GGUF to model-backups/ (if not already there),
#      then delete it from models/ (superseded by R13)
#
# SAFETY: R12 is snapshotted to ~/Desktop/model-backups/ before this round
# drops it (set SKIP_R12_GUARD=1 to override).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND13="$CLOUD/out/round13"
MERGED="$ROUND13/merged"
ADAPTER="$ROUND13/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-7B-Instruct-Uncensored"
F16="$ROUND13/$NAME.R13.F16.gguf"
Q4="$ROUND13/$NAME.R13.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R13.Q4_K_M.gguf"
OLD_R12="$MODELS/$NAME.R12.Q4_K_M.gguf"
BACKUP_R12="$BACKUP_DIR/$NAME.R12.Q4_K_M.2026-08-10.gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-13 deploy ==="
[ -f "$MERGED/model.safetensors.index.json" ] || { echo "❌ No merged model — run the round-13 download step first" >&2; exit 1; }
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R12 backup must exist before we can drop R12 ─────────
if [ ! -f "$BACKUP_R12" ]; then
  if [ -f "$OLD_R12" ]; then
    echo "--- [0/5] backing up the live R12 GGUF ---"
    cp -n "$OLD_R12" "$BACKUP_R12"
    echo "   ✓ backed up: $BACKUP_R12"
  else
    echo "⚠️  R12 not found at $OLD_R12 and no backup at $BACKUP_R12." >&2
    echo "   (Proceed anyway? Set SKIP_R12_GUARD=1 to override.)" >&2
    [ "${SKIP_R12_GUARD:-0}" = "1" ] || exit 1
  fi
else
  echo "   ✓ R12 backup already present: $BACKUP_R12"
fi

# ─── 1. Convert (HF -> F16 GGUF) ───────────────────────────────────────────
for tf in tokenizer.json tokenizer_config.json chat_template.jinja README.md; do
  if [ ! -f "$MERGED/$tf" ] && [ -f "$ADAPTER/$tf" ]; then
    cp "$ADAPTER/$tf" "$MERGED/$tf"
    echo "   (copied missing $tf from adapter -> merged)"
  fi
done

# ─── 1b. Strip stale QLoRA quant metadata ─────────────────────────────
# merge_and_unload() leaves quantization_config (bitsandbytes) in config.json
# even though the weights are fp16 — convert_hf_to_gguf refuses it.
python3 - "$MERGED/config.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
if "quantization_config" in d:
    del d["quantization_config"]
    json.dump(d, open(p, "w", encoding="utf-8"), indent=2)
    print("   (stripped stale quantization_config — weights are fp16)")
PY

# ─── 1a. HF tokenizer compat shim ────────────────────────────────────────
python3 - "$MERGED/tokenizer_config.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
e = d.get("extra_special_tokens")
if isinstance(e, list):
    d["extra_special_tokens"] = {t: t for t in e}
    json.dump(d, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("   (normalized extra_special_tokens: list -> dict)")
PY

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

# ─── 4. Health check (retry loop) + smoke ──────────────────────────────────
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

# ─── 5. Drop the superseded R12 ─────────────────────────────────────────────
echo "--- [5/5] removing superseded R12 model copy ---"
rm -f "$OLD_R12"
echo "   ✓ deleted: $OLD_R12"
echo "   (R12 backup preserved at: $BACKUP_R12 — restore anytime via scripts/dspark-target.env)"

echo ""
echo "✅ Round-13 model deployed. dspark now serves R13 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
echo "   Old R12 GGUF removed from models/. (stock + R6 + R11 GGUFs untouched)"
