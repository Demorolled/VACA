#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-11 merged safetensors -> q4_k_m GGUF, deploy to dspark,
# then drop the old R10 model that is superseded.
# =============================================================================
# Prereq:  fetch the round-11 kernel output into training/cloud/out/round11/:
#          out/round11/adapter/   (adapter_round11 — LoRA for future chaining)
#          out/round11/merged/    (merged 16-bit safetensors + config/tokenizer)
#          The round-10 downloader (scripts/download-round10-merged.py) is
#          hard-wired to the round-10 kernel — pull the round-11 files from
#          the Kaggle Output tab (or point a copy at vaca-qlora-round11).
#
# Steps:
#   1. convert_hf_to_gguf.py (unsloth llama.cpp)  -> R11.F16.gguf
#   2. llama-quantize q4_k_m                       -> R11.Q4_K_M.gguf
#   3. copy to models/, point dspark at it, restart (tmux:dspark)
#   4. health-check + smoke generation
#   5. delete the OLD R10 GGUF from models/ (superseded by R11)
#
# The round-11 adapter is kept for chaining; the F16 intermediate is removed
# after quantization to save ~15 GB.
#
# SAFETY: R10 is snapshotted at ~/Desktop/model-backups/ (2026-08-10) before
# this round — the old-model deletion below is safe, but double-check the
# backup exists first (sha256 bc6b21a5…).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND11="$CLOUD/out/round11"
MERGED="$ROUND11/merged"
ADAPTER="$ROUND11/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-7B-Instruct-Uncensored"
F16="$ROUND11/$NAME.R11.F16.gguf"
Q4="$ROUND11/$NAME.R11.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R11.Q4_K_M.gguf"
OLD_R10="$MODELS/$NAME.R10.Q4_K_M.gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-11 deploy ==="
[ -f "$MERGED/model.safetensors.index.json" ] || { echo "❌ No merged model — run the round-11 download step first" >&2; exit 1; }
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R10 backup must exist before we can drop R10 ─────────
if [ ! -f "$BACKUP_DIR/$NAME.R10.Q4_K_M.2026-08-10.gguf" ]; then
  echo "⚠️  R10 backup not found at $BACKUP_DIR — aborting the R10 drop." >&2
  echo "   (Deploy R11 anyway? Set SKIP_R10_GUARD=1 to override.)" >&2
  [ "${SKIP_R10_GUARD:-0}" = "1" ] || exit 1
fi

# ─── 1. Convert (HF -> F16 GGUF) ───────────────────────────────────────────
# Safeguard: save_pretrained_merged may not write tokenizer files into the
# merged dir — copy them from the adapter if missing (convert needs them).
for tf in tokenizer.json tokenizer_config.json chat_template.jinja README.md; do
  if [ ! -f "$MERGED/$tf" ] && [ -f "$ADAPTER/$tf" ]; then
    cp "$ADAPTER/$tf" "$MERGED/$tf"
    echo "   (copied missing $tf from adapter -> merged)"
  fi
done

# ─── 1a. HF tokenizer compat shim ────────────────────────────────────────
# Unsloth/Kaggle now save "extra_special_tokens" as a LIST, but the local
# transformers (4.57.6) feeds it into _set_model_specific_special_tokens()
# which expects a dict ('list' object has no attribute 'keys'). All those
# tokens already exist in added_tokens_decoder, so rewrite to the dict form
# the installed transformers accepts. Idempotent.
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

# ─── 5. Drop the superseded R10 ─────────────────────────────────────────────
echo "--- [5/5] removing superseded R10 model copy ---"
rm -f "$OLD_R10"
echo "   ✓ deleted: $OLD_R10"
echo "   (R10 backup preserved at: $BACKUP_DIR — restore anytime via scripts/dspark-target.env)"

echo ""
echo "✅ Round-11 model deployed. dspark now serves R11 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
echo "   Old R10 GGUF removed from models/. (stock + R6 GGUFs untouched)"
