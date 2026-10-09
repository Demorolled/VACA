#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-chain-r13.sh — run R13 training immediately after R12 completes
# =============================================================================
# A single daemon that orchestrates the handoff:
#
#   1. WAIT for the round-12 kernel (vaca-qlora-round12) to leave RUNNING
#      (poll every 5 min, alert on state change).
#   2. DOWNLOAD the R12 artifacts (adapter + merged safetensors) via
#      scripts/download-round12-merged.py (range-resume, retries).
#   3. DEPLOY R12 to dspark via scripts/deploy-round12.sh (convert → q4_k_m →
#      dspark :8000 → back up + drop R11).   [R12 now serves the app]
#   4. STAGE the R12 trained LoRA (out/round12/adapter — genuinely trained,
#      thanks to the save-bug fix) + tokenizer files, upload as dataset
#      <user>/vaca-r12-adapter.
#   5. PUSH the round-13 kernel <user>/vaca-qlora-round13 (resumes from the
#      R12 adapter). Reruns the setup script so ordering is handled.
#   6. START the round-13 watchdog (scripts/kaggle-watch-round13.sh) which
#      auto-downloads + deploys R13 when it completes.
#
# Usage:
#   bash scripts/kaggle-chain-r13.sh               # run the whole chain
#   bash scripts/kaggle-chain-r13.sh --no-deploy   # download, upload adapter,
#                                                  # push R13, but skip dspark
#                                                  # deployment of R12
#
# Log: /tmp/kaggle-chain-r13.log   (KAGGLE_CHAIN_LOG to override)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

NO_DEPLOY=0
[ "${1:-}" = "--no-deploy" ] && NO_DEPLOY=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KAGGLE_DIR="$CLOUD_DIR/kaggle"
LOG="${KAGGLE_CHAIN_LOG:-/tmp/kaggle-chain-r13.log}"
POLL="${KAGGLE_WATCH_POLL:-300}"

R12_KERNEL="stevenawoods/vaca-qlora-round12"
R13_KERNEL="stevenawoods/vaca-qlora-round13"
R12_OUT="$CLOUD_DIR/out/round12"
R12_ADAPTER_SRC="$R12_OUT/adapter"
R12_MERGED_SRC="$R12_OUT/merged"

ADAPTER_SLUG="vaca-r12-adapter"
ADAPTER_META="r12-adapter-dataset-metadata.json"

log() { echo "[chain-r13] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# ─── Credentials ────────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
[ -n "$USERNAME" ] || { log "❌ could not determine Kaggle username"; exit 2; }
R12_KERNEL="${USERNAME}/${R12_KERNEL#*/}"
R13_KERNEL="${USERNAME}/${R13_KERNEL#*/}"

log "chain started — username=$USERNAME deploy=$([ "$NO_DEPLOY" = 1 ] && echo OFF || echo ON)"

# ─── 1. Wait for R12 to finish ─────────────────────────────────────────────
PREV=""
i=0
while [ $i -lt 150 ]; do
  i=$((i+1))
  STATUS="$(timeout 30 kaggle kernels status "$R12_KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo 'UNKNOWN')"
  if [ -n "$PREV" ] && [ "$STATUS" != "$PREV" ]; then
    log "🚨 status changed: $PREV → $STATUS"
  fi
  log "poll #$i — $R12_KERNEL: $STATUS"
  PREV="$STATUS"
  case "$STATUS" in
    *RUNNING*|*PENDING*|*UNKNOWN*) sleep "$POLL" ;;
    *) break ;;
  esac
done

if [[ "$STATUS" != *COMPLETE* && "$STATUS" != *SUCCESS* && "$STATUS" != *DONE* ]]; then
  log "⚠️  R12 ended as '$STATUS' — attempting artifact recovery anyway."
fi

# ─── 2. Download R12 artifacts ─────────────────────────────────────────────
log "⬇️  downloading R12 artifacts..."
if ! python3 "$SCRIPT_DIR/download-round12-merged.py" all 2>&1 | tee -a "$LOG" | grep -q '✅ ALL round-12 artifacts downloaded'; then
  log "❌ R12 download failed — rerun: python3 $SCRIPT_DIR/download-round12-merged.py all"
  exit 1
fi
[ -f "$R12_ADAPTER_SRC/adapter_model.safetensors" ] || { log "❌ R12 adapter missing after download"; exit 1; }
log "✅ R12 adapter + merged downloaded."

# ─── 3. Deploy R12 to dspark (unless --no-deploy) ─────────────────────────
if [ "$NO_DEPLOY" = "1" ]; then
  log "⏭️  --no-deploy — skipping dspark deployment of R12."
else
  log "🔄 deploying R12 (convert → q4_k_m → dspark → drop R11)..."
  if bash "$SCRIPT_DIR/deploy-round12.sh" 2>&1 | tee -a "$LOG" | grep -q '✅ Round-12 model deployed'; then
    log "✅ R12 DEPLOYED — dspark now serves R12; R11 backed up and dropped."
  else
    log "⚠️  R12 deploy did not finish cleanly — inspect above; continuing chain."
  fi
fi

# ─── 4. Upload the R12 adapter as dataset B ────────────────────────────────
log "⬆️  staging + uploading ${USERNAME}/$ADAPTER_SLUG (R12 trained LoRA)..."
ADAPTER_DIR="$(mktemp -d)"
cp "$R12_ADAPTER_SRC"/adapter_config.json "$R12_ADAPTER_SRC"/adapter_model.safetensors "$ADAPTER_DIR/" 2>/dev/null || true
for tf in tokenizer.json tokenizer_config.json chat_template.jinja; do
  [ -f "$R12_MERGED_SRC/$tf" ] && cp "$R12_MERGED_SRC/$tf" "$ADAPTER_DIR/" || true
done
printf '# VACA R12 LoRA adapter (trained, defects round)\nResume point for round 13. Chained from R11 (e3b7e7cc). Trained on round-12 Mix (74 rows, LR 5e-5, seq 3072, 3 ep, accum 4).\n' > "$ADAPTER_DIR/README.md"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$ADAPTER_META" > "$ADAPTER_DIR/dataset-metadata.json"

if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" >/dev/null 2>&1; then
  timeout 240 kaggle datasets version -p "$ADAPTER_DIR" -m "Refresh: R12 trained LoRA" 2>&1 | tail -3
else
  timeout 180 kaggle datasets create -p "$ADAPTER_DIR" 2>&1 | tail -3
fi
rm -rf "$ADAPTER_DIR"
log "✅ adapter dataset uploaded — waiting for it to become ready (up to ~15 min)..."
ADAPTER_READY=0
for w in $(seq 1 30); do
  sleep 30
  if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" 2>/dev/null | grep -q ready; then
    log "✅ $ADAPTER_SLUG ready after ~$((w * 30))s"
    ADAPTER_READY=1
    break
  fi
done
[ "$ADAPTER_READY" = "1" ] || log "⚠️  adapter still not 'ready' after 15 min — will still attempt the push."

# ─── 5. Push the R13 kernel — loop until confirmed (setup checks 'ready') ──
PUSHED=0
for attempt in 1 2 3 4 5 6; do
  log "🚀 pushing round-13 kernel (attempt $attempt/6)..."
  if bash "$SCRIPT_DIR/kaggle-setup-round13.sh" 2>&1 | tee -a "$LOG" | grep -q 'Kernel pushed'; then
    PUSHED=1
    log "✅ R13 kernel pushed: https://www.kaggle.com/code/$R13_KERNEL"
    break
  fi
  log "⚠️  kernel push not confirmed (adapter may still be propagating) — waiting 2 min..."
  sleep 120
done
if [ "$PUSHED" != "1" ]; then
  log "❌ R13 kernel push failed after 6 attempts — check: kaggle datasets status $USERNAME/$ADAPTER_SLUG"
fi

# ─── 6. Start the R13 watchdog (auto download + deploy when R13 completes) ─
if [ "$PUSHED" = "1" ]; then
  log "👀 starting round-13 watchdog (tmux:watch13)..."
  tmux kill-session -t watch13 2>/dev/null || true
  tmux new-session -d -s watch13 \
    "cd $PROJECT_ROOT && bash $SCRIPT_DIR/kaggle-watch-round13.sh > /tmp/kaggle-watch-round13.log 2>&1"
  sleep 3
  log "✅ chain complete — R13 training queued/started; watchdog live in tmux:watch13."
  log "   status: kaggle kernels status $R13_KERNEL"
else
  log "❌ chain ended — R13 kernel NOT pushed; no watchdog started."
  log "   fix: bash $SCRIPT_DIR/kaggle-setup-round13.sh   (once $ADAPTER_SLUG is ready)"
fi
