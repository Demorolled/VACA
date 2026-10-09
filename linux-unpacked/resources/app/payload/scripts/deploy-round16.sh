#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Convert the round-16 merged safetensors -> q4_k_m GGUF, deploy to dspark,
# then drop the old R15 model that is superseded.
# =============================================================================
# Prereq:  fetch the round-16 kernel output into training/cloud/out/round16/:
#          out/round16/adapter/   (adapter_round16 — LoRA for future chaining)
#          out/round16/merged/    (REAL fp16 merged — via
#                                  scripts/build-r16-merged.py)
#
# Steps:
#   1. convert_hf_to_gguf.py (unsloth llama.cpp)  -> R16.F16.gguf
#   2. llama-quantize q4_k_m                       -> R16.Q4_K_M.gguf
#   3. copy to models/, point dspark at it, restart (tmux:dspark)
#   4. health-check + smoke generation
#   5. BACK UP the old R15 GGUF to model-backups/ (if not already there),
#      then delete it from models/ (superseded by R16)
#
# SAFETY: R15 is snapshotted to ~/Desktop/model-backups/ before this round
# drops it (set SKIP_R15_GUARD=1 to override).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$PROJECT_ROOT/training/cloud"
ROUND16="$CLOUD/out/round16"
MERGED="$ROUND16/merged"
ADAPTER="$ROUND16/adapter"
MODELS="$PROJECT_ROOT/models"
BACKUP_DIR="$PROJECT_ROOT/../model-backups"

NAME="Qwen2.5-7B-Instruct-Uncensored"
F16="$ROUND16/$NAME.R16.F16.gguf"
Q4="$ROUND16/$NAME.R16.Q4_K_M.gguf"
DEPLOY_Q4="$MODELS/$NAME.R16.Q4_K_M.gguf"
OLD_R15="$MODELS/$NAME.R15.Q4_K_M.gguf"
BACKUP_R15="$BACKUP_DIR/$NAME.R15.Q4_K_M.2026-08-13.gguf"

LLAMA_CPP="$HOME/.unsloth/llama.cpp"
CONVERT="$LLAMA_CPP/convert_hf_to_gguf.py"
QUANTIZE="$LLAMA_CPP/llama-quantize"

echo "=== Round-16 deploy ==="
# Merged output may be a sharded checkpoint (model.safetensors.index.json) OR a
# single-file checkpoint (model.safetensors) — accept both.
if [ ! -f "$MERGED/model.safetensors.index.json" ] && [ ! -f "$MERGED/model.safetensors" ]; then
  echo "❌ No merged model — run download-round16-merged.py + build-r16-merged.py first" >&2
  exit 1
fi

# KEEP_R15=1 — deploy R16 but leave the old R15 GGUF in models/ untouched
# (no backup copy, no deletion). Default (0) keeps the original behavior:
# back up R15 to model-backups/ first, then drop it from models/.
if [ "${KEEP_R15:-0}" = "1" ]; then
  echo "   KEEP_R15=1 — R15 stays in models/ (skipping backup + deletion)"
fi
[ -f "$CONVERT" ] && [ -x "$QUANTIZE" ] || { echo "❌ llama.cpp toolchain missing ($CONVERT / $QUANTIZE)" >&2; exit 1; }

# ─── 0. Safety guard: R15 backup must exist before we can drop R15 ─────────
# (skipped entirely when KEEP_R15=1 — nothing will be dropped)
if [ "${KEEP_R15:-0}" != "1" ]; then
  if [ ! -f "$BACKUP_R15" ]; then
    if [ -f "$OLD_R15" ]; then
      echo "--- [0/5] backing up the live R15 GGUF ---"
      cp -n "$OLD_R15" "$BACKUP_R15"
      echo "   ✓ backed up: $BACKUP_R15"
    else
      echo "⚠️  R15 not found at $OLD_R15 and no backup at $BACKUP_R15." >&2
      echo "   (Proceed anyway? Set SKIP_R15_GUARD=1 to override.)" >&2
      [ "${SKIP_R15_GUARD:-0}" = "1" ] || exit 1
    fi
  else
    echo "   ✓ R15 backup already present: $BACKUP_R15"
  fi
fi

# ─── 1. Tokenizer files may live only in the adapter dir ───────────────────
for tf in tokenizer.json tokenizer_config.json chat_template.jinja README.md; do
  if [ ! -f "$MERGED/$tf" ] && [ -f "$ADAPTER/$tf" ]; then
    cp "$ADAPTER/$tf" "$MERGED/$tf"
    echo "   (copied missing $tf from adapter -> merged)"
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
  if echo "$HEALTH" | grep -q '"status":"ok"'; then
    HEALTH_OK=1
    echo "   attempt $attempt: OK"
    break
  fi
  echo "   attempt $attempt: not ready yet"
done
if [ "$HEALTH_OK" != "1" ]; then
  echo "   ❌ dspark health never OK after 5 attempts. tail -40 $PROJECT_ROOT/scripts/dspark.log" >&2
  exit 1
fi

echo "   Smoke generation test (may take ~90s)..."
SMOKE="$(curl -s -m 90 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"x","messages":[{"role":"user","content":"Reply with the single word: OK"}],"max_tokens":10}' 2>&1 || true)"
if echo "$SMOKE" | grep -q '"content"'; then
  echo "   ✓ OK"
else
  echo "   ⚠️  smoke response unexpected: ${SMOKE:0:120}"
fi

# ─── 5. Drop the superseded R15 (unless KEEP_R15=1) ────────────────────────
if [ "${KEEP_R15:-0}" = "1" ]; then
  echo "--- [5/5] KEEP_R15=1 — keeping R15 in models/ (no deletion) ---"
elif [ -f "$OLD_R15" ]; then
  echo "--- [5/5] removing superseded R15 model copy ---"
  rm -f "$OLD_R15"
  echo "   ✓ deleted: $OLD_R15"
  echo "   (R15 backup preserved at: $BACKUP_R15 — restore anytime via scripts/dspark-target.env)"
else
  echo "   (no R15 copy to delete)"
fi

echo ""
echo "✅ Round-16 model deployed. dspark now serves R16 on :8000."
echo "   Adapter kept at: $ADAPTER (for future chaining)"
