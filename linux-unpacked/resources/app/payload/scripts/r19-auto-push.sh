#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# R19 auto-push: wait for the capture session to finish, build the corpus,
# then push corpus + kernel to Kaggle. Logs to /tmp/r19-autopush.log.
#
#   bash scripts/r19-auto-push.sh                # watch + push (long-running)
#   bash scripts/r19-auto-push.sh --once         # skip waiting; push now
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

LOG="${R19_AUTOPUSH_LOG:-/tmp/r19-autopush.log}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD="$ROOT/training/cloud"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

log "R19 auto-push started (once=$ONCE)"

# ─── 1. Wait for the capture session to finish ─────────────────────────────
if [ "$ONCE" = "0" ]; then
  log "Waiting for capture session (run-r19-capture.py)..."
  while pgrep -f "run-r19-capture.py" >/dev/null 2>&1; do
    sleep 60
  done
  log "Capture session finished."
  # give the final capture a moment to flush
  sleep 5
fi

# ─── 2. Build the corpus ───────────────────────────────────────────────────
log "Building round-19 corpus (1,900-row cap)..."
if ! python3 "$SCRIPT_DIR/build-r19-corpus.py" 2>&1 | tail -20 | tee -a "$LOG"; then
  log "❌ corpus build failed — aborting."
  exit 1
fi
[ -f "$CLOUD/round19-train.jsonl" ] || { log "❌ round19-train.jsonl missing after build — aborting."; exit 1; }
log "✅ Corpus built: $(wc -l < "$CLOUD/round19-train.jsonl") rows"

# ─── 3. Build the notebook (reads round19.meta.json) ───────────────────────
log "Building round-19 Kaggle notebook..."
python3 "$SCRIPT_DIR/build-round19-kaggle-notebook.py" 2>&1 | tail -3 | tee -a "$LOG"

# ─── 4. Push the R18 adapter (kernel resumes it — never pushed after R18) ─
ADAPTER_DIR="$CLOUD/out/round18/adapter"
ADAPTER_SLUG="vaca-r18-adapter"
if timeout 60 kaggle datasets status "stevenawoods/$ADAPTER_SLUG" >/dev/null 2>&1; then
  log "Adapter $ADAPTER_SLUG already on Kaggle — skipping."
else
  if [ -d "$ADAPTER_DIR" ] && [ -f "$ADAPTER_DIR/adapter_config.json" ]; then
    log "Pushing R18 adapter as $ADAPTER_SLUG (flat zip)..."
    ADZIP="$(mktemp -d)"
    (cd "$ADAPTER_DIR" && zip -qr "$ADZIP/adapter.zip" .)
    cat > "$ADZIP/dataset-metadata.json" <<EOF
{
  "id": "stevenawoods/$ADAPTER_SLUG",
  "title": "VACA R18 QLoRA adapter (14B coder)",
  "subtitle": "R18 trained LoRA — chained resume for Round-19",
  "licenses": [{ "name": "other" }]
}
EOF
    if timeout 60 kaggle datasets status "stevenawoods/$ADAPTER_SLUG" >/dev/null 2>&1; then
      timeout 240 kaggle datasets version -p "$ADZIP" -m "Refresh: R18 adapter (R19 resume)" 2>&1 | tail -3 | tee -a "$LOG"
    else
      timeout 240 kaggle datasets create -p "$ADZIP" 2>&1 | tail -3 | tee -a "$LOG"
    fi
    rm -rf "$ADZIP"
    log "Adapter push done."
  else
    log "❌ R18 adapter not found at $ADAPTER_DIR — cannot resume chain. Aborting."
    exit 1
  fi
fi

# ─── 5. Push corpus + kernel to Kaggle ─────────────────────────────────────
log "Pushing corpus + kernel to Kaggle (kaggle-setup-round19.sh)..."
if bash "$SCRIPT_DIR/kaggle-setup-round19.sh" 2>&1 | tee -a "$LOG"; then
  log "✅ Kaggle push complete — kernel live at https://www.kaggle.com/code/stevenawoods/vaca-qlora-round19"
else
  log "❌ Kaggle push failed — see $LOG"
  exit 1
fi

log "DONE — R19 corpus + kernel pushed."
