#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# auto-deploy-r23.sh — deploy R23 the moment training finishes (disconnect-proof)
# =============================================================================
# Watches the R23 training process; when it exits (success or fail) it runs the
# proven R21/R22 chain on the agent:
#   1. merge  : LoRA adapter → full 16-bit weights (unsloth merged_16bit, 3 GPUs)
#   2. convert: llama.cpp convert_hf_to_gguf.py → Q8_0
#   3. quant  : llama-quantize → Q4_K_M (same quantization as R20/R22)
#   4. ollama : create vaca-r23:latest from the GGUF (blob store)
#   5. dspark : DSPARK_TARGET=vaca-r23:latest + restart + health check
#   6. gate   : A/B regression gate (ab-test-tuned-vs-stock.py --gate)
#   7. audit  : claims audit vs live app (baseline: R22 = 213/250, 0 failures)
#   8. cleanup: delete merged/ + Q8 intermediates (keep Q4 GGUF + adapter)
# Every step is logged to training/cloud/round23-deploy.log.
#
# Usage (ON THE AGENT, detached — survives SSH/VNC drops):
#   setsid bash scripts/auto-deploy-r23.sh > training/cloud/round23-deploy.log 2>&1 < /dev/null &
#
# Monitor from anywhere:
#   tail -f ~/Desktop/visual-ai-architect/training/cloud/round23-deploy.log
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."

VENV_BIN="$(pwd)/llm-training-app/.venv/bin"
ROUND23="$(pwd)/training/cloud/out/round23"
ADAPTER="$ROUND23/final"
MERGED="$ROUND23/merged"
GGUF_DIR="$ROUND23/gguf"
GGUF_Q8="$GGUF_DIR/vaca-r23.Q8_0.gguf"
GGUF_Q4="$GGUF_DIR/vaca-r23.Q4_K_M.gguf"
CONVERT="$HOME/.unsloth/llama.cpp/convert_hf_to_gguf.py"
QUANT="$HOME/.unsloth/llama.cpp/llama-quantize"
ENV_FILE="scripts/dspark-target.env"
OLLAMA_NAME="vaca-r23:latest"
START_TS="$(date +%s)"
LOG_LINE="[$(date +%H:%M:%S)]"

say()  { echo "$LOG_LINE $*"; }
fail() { say "❌ $*"; echo "ROLLBACK: bash scripts/dspark-model.sh 22   (restores R22)"; exit 1; }

say "=== R23 auto-deploy watcher started $(date) ==="
say "watching for training exit (pid pattern train_r23.py)…"

# ── 0. wait for training to finish ──────────────────────────────────────────
while pgrep -f "train_r23.py" >/dev/null 2>&1; do
  sleep 60
done
say "training process exited."

# Grace: adapter may still be flushing; wait up to 30 min for it.
waited=0
while [ ! -f "$ADAPTER/adapter_model.safetensors" ]; do
  if [ "$waited" -ge 1800 ]; then
    fail "adapter never appeared at $ADAPTER — training may have failed. tail training/cloud/round23-train.log"
  fi
  sleep 60; waited=$((waited + 60))
done
say "✅ adapter found: $ADAPTER"

# ── 1. merge ────────────────────────────────────────────────────────────────
say "── [1/5] merging LoRA → 16-bit (3 GPUs, ~10 min) ──"
"$VENV_BIN/python" scripts/build-r23-merged.py || fail "merge failed"
df -h / | tail -1

# ── 2+3. convert + quantize ─────────────────────────────────────────────────
mkdir -p "$GGUF_DIR"
[ -x "$QUANT" ] || [ -f "$QUANT" ] || fail "llama-quantize missing at $QUANT"
say "── [2/5] convert → Q8_0 (~10 min) ──"
python3 "$CONVERT" "$MERGED" --outfile "$GGUF_Q8" --outtype q8_0 || fail "convert failed"
say "── [3/5] quantize → Q4_K_M (~10 min) ──"
"$QUANT" "$GGUF_Q8" "$GGUF_Q4" q4_k_m --allow-requantize || fail "quantize failed"
Q4_SIZE="$(stat -c %s "$GGUF_Q4")"
[ "$Q4_SIZE" -gt 8000000000 ] || fail "Q4 GGUF only ${Q4_SIZE} bytes — refusing to deploy partial export"
say "✅ Q4_K_M GGUF: $(du -h "$GGUF_Q4" | cut -f1)"

# ── 4. ollama create ────────────────────────────────────────────────────────
say "── [4/5] ollama create $OLLAMA_NAME ──"
cat > "$GGUF_DIR/Modelfile" <<EOF
FROM $GGUF_Q4
TEMPLATE {{ .Prompt }}
PARAMETER num_ctx 8192
EOF
ollama create vaca-r23 -f "$GGUF_DIR/Modelfile" || fail "ollama create failed"
ollama list | grep vaca-r23 || fail "vaca-r23 not in ollama list"

# ── 5. point dspark at R23 + restart ────────────────────────────────────────
say "── [5/5] dspark → $OLLAMA_NAME ──"
echo "DSPARK_TARGET=$OLLAMA_NAME" > "$ENV_FILE"
# Keep the toggle script in sync: insert a 23 case if not present.
if ! grep -q "vaca-r23" scripts/dspark-model.sh; then
  python3 - <<'PYEOF'
import re
p = "scripts/dspark-model.sh"
s = open(p).read()
if "vaca-r23" not in s:
    block = ("  23|r23|latest)\n"
             "    apply \"vaca-r23:latest\" \"vaca-r23 — NEWEST tuned 14B (R23: reasoning + bible-code)\"\n"
             "    ;;\n")
    s = re.sub(r'(\n\s*22\|r22\|latest\|22b\))', '\n' + block.rstrip('\n') + r'\1', s, count=1)
    s = s.replace("  22|r22|latest|22b)", "  22|r22|22b)")
    open(p, "w").write(s)
    print("  dspark-model.sh: added 23 case")
else:
    print("  dspark-model.sh: 23 case already present")
PYEOF
fi
sudo systemctl restart dspark || fail "dspark restart failed"
say "  waiting for dspark health…"
up=0
for _ in $(seq 1 36); do
  sleep 5
  if curl -s --max-time 3 http://127.0.0.1:8000/v1/health >/dev/null 2>&1; then up=1; break; fi
done
[ "$up" = 1 ] || fail "dspark did not come up within 3 min"
say "✅ dspark is UP — $(curl -s --max-time 3 http://127.0.0.1:8000/v1/models | head -c 200)"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | sed 's/^/  GPU /'

# ── 6. A/B regression gate ──────────────────────────────────────────────────
say "── A/B regression gate (tuned vs stock) ──"
if python3 scripts/ab-test-tuned-vs-stock.py --gate; then
  say "✅ A/B gate PASSED"
else
  say "⚠️  A/B gate FAILED — R23 still serving; see data/ab-test/ for details. Rollback: bash scripts/dspark-model.sh 22"
fi

# ── 7. claims audit (baseline R22 = 213/250, 0 failures) ────────────────────
if curl -s --max-time 3 http://127.0.0.1:3001/api/health >/dev/null 2>&1; then
  say "── claims audit vs live app (takes ~5-10 min) ──"
  python3 scripts/audit-claims.py | tail -30 || say "⚠️  audit failed to run"
  python3 - <<'EOF' || true
import json
try:
    d = json.load(open("data/claims-audit.json"))
    fails = [r["claim"] for r in d["results"] if not r["passed"]]
    print(f"AUDIT RESULT: {d['total']}/{d['max']} ({d['pct']}%) — R22 baseline was 213/250")
    print(f"failures: {fails if fails else 'NONE'}")
except Exception as e:
    print("could not parse audit:", e)
EOF
else
  say "⚠️  backend :3001 not up — skipped claims audit (run: python3 scripts/audit-claims.py)"
fi

# ── 8. cleanup intermediates (keep Q4 GGUF + adapter + ollama blob) ─────────
say "── cleanup ──"
rm -rf "$MERGED" "$GGUF_Q8"
say "  removed merged/ + Q8 ($(du -sh "$MERGED" "$GGUF_Q8" 2>/dev/null | head -1))"
df -h / | tail -1

say "✅✅ R23 DEPLOY COMPLETE — $(date)"
say "  serving: $(grep -m1 '^DSPARK_TARGET=' "$ENV_FILE")"
say "  rollback: bash scripts/dspark-model.sh 22"
echo "DEPLOY_DONE at $(date)" > "training/cloud/round23-deploy.done"
