#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Chain the NEXT VACA round after the current kernel completes on Kaggle.
# =============================================================================
# v6 flow (single-GPU, ROUNDS=1 — see build-kaggle-notebook.py): each kernel
# run trains exactly ONE round (~6-10 h, safely under Kaggle's 12 h cap), and
# the 4 rounds are chained across runs. This script:
#
#  1. Polls the CURRENT kernel until it finishes (up to 15 h).
#  2. Downloads its Output, finds the HIGHEST completed adapter (adapter_roundN
#     with highest N; fallback adapter/ = copy of the last round).
#  3. Zips the adapter CONTENTS at the zip root (adapter_config.json + weights).
#  4. Uploads it as the dataset  <user>/vaca-rounds12-adapter
#     (create → version fallback, like the main dataset).
#  5. Pushes the NEXT kernel mode:
#        last round 1 → --kernel round2    (vaca-qlora-rounds-1-2)
#        last round 2 → --kernel rounds34  (vaca-qlora-rounds-3-4)
#        last round 3 → --kernel round4    (vaca-qlora-rounds-3-4)
#        last round 4 → nothing — all 4 rounds done
#     ⚠️ The API push IGNORES the metadata GPU/internet flags — they must be set
#     manually in the web UI (Settings → Accelerator → GPU T4 x2, Internet → ON).
#
# Kernel refs: rounds 1-2 share the vaca-qlora-rounds-1-2 slug, rounds 3-4 the
# vaca-qlora-rounds-3-4 slug (titles slugify exactly — see the builder).
#
# Usage:
#   bash scripts/kaggle-chain-rounds.sh            # wait + chain (long-running)
#   bash scripts/kaggle-chain-rounds.sh --poll-min 60
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-chain-rounds.sh
#
# Exit codes: 0 = next kernel pushed (or all 4 rounds done) · 1 = kernel
#             failed/no output · 2 = creds · 3 = usage
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

POLL_MIN="${POLL_MIN:-600}"     # seconds between status polls (default 10 min)
MAX_WAIT_MIN="${MAX_WAIT_MIN:-900}"  # max minutes to wait for the kernel (15 h)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KAGGLE_DIR="$CLOUD_DIR/kaggle"
ADAPTER_DS="vaca-rounds12-adapter"

# Which kernel to watch: default = rounds 1-2 (round 1), overridable so the
# script can be pointed at a resume kernel (e.g. --kernel round2).
KERNEL_MODE="${KERNEL_MODE:-rounds12}"
case "$KERNEL_MODE" in
  rounds12) WATCH_SLUG="vaca-qlora-rounds-1-2" ;;
  round2)   WATCH_SLUG="vaca-qlora-rounds-1-2" ;;
  rounds34) WATCH_SLUG="vaca-qlora-rounds-3-4" ;;
  round4)   WATCH_SLUG="vaca-qlora-rounds-3-4" ;;
  *) echo "❌ KERNEL_MODE must be rounds12|round2|rounds34|round4 (got: $KERNEL_MODE)" >&2; exit 3 ;;
esac

# ─── 1. Credentials ────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or access_token)." >&2
  exit 2
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 2
fi
echo "✅ Kaggle username: $USERNAME"

# ─── Status parsing ────────────────────────────────────────────────────────
# Robust status extractor for BOTH CLI output shapes:
#   kernels status →  '… has status "KernelWorkerStatus.RUNNING"'  (enum prefix)
#   datasets status →  'ready'                                       (bare word)
# Returns the word after the last dot, lowercased (RUNNING / complete → running).
status_word() {
  timeout 30 "$@" 2>/dev/null \
    | grep -oP '(status\s+"[^"]+"|^[A-Za-z]+$)' \
    | head -1 \
    | tr -d '"' \
    | sed 's/.*\.//' \
    | tr '[:upper:]' '[:lower:]' \
    || true   # keep the watcher alive through transient API blips
}

# ─── 2. Wait for the current kernel ────────────────────────────────────────
echo "⏳ Waiting for $USERNAME/$WATCH_SLUG to finish (polling every ${POLL_MIN}s)..."
START=$(date +%s)
while true; do
  STATUS="$(status_word kaggle kernels status "$USERNAME/$WATCH_SLUG")"
  [ -z "$STATUS" ] && STATUS="unknown"
  echo "  [$(date +%H:%M:%S)] kernel status: $STATUS"
  case "$STATUS" in
    complete|succeeded|success) echo "✅ Kernel finished: $STATUS"; break ;;
    error|failed|canceled)
      echo "❌ Kernel is $STATUS — stopping chain." >&2
      echo "   Check: https://www.kaggle.com/code/$USERNAME/$WATCH_SLUG" >&2
      exit 1 ;;
  esac
  ELAPSED=$(( ($(date +%s) - START) / 60 ))
  if [ "$ELAPSED" -ge "$MAX_WAIT_MIN" ]; then
    echo "❌ Timed out after ${MAX_WAIT_MIN}m — kernel still not done." >&2
    exit 1
  fi
  sleep "$POLL_MIN"
done

# ─── 3. Download output + find the HIGHEST completed adapter ───────────────
OUT_DIR="$(mktemp -d)"
echo "📥 Downloading kernel output (includes ~4.4 GB GGUF — can take a while)..."
# timeout generous: results.zip embeds the ~4.4 GB GGUF
if ! timeout 1800 kaggle kernels output "$USERNAME/$WATCH_SLUG" -p "$OUT_DIR" 2>&1 | tail -2; then
  echo "❌ Output download failed/timed out — try again later." >&2
  exit 1
fi

# Kaggle auto-zips /kaggle/working into kernel-output.zip, and the trainer
# writes out/results.zip inside it. Unpack any wrapper zips, then find
# results.zip anywhere and extract IT too.
if [ -f "$OUT_DIR/kernel-output.zip" ]; then
  echo "   Unpacking kernel-output.zip ..."
  (cd "$OUT_DIR" && python3 -c "import zipfile; zipfile.ZipFile('kernel-output.zip').extractall('.')")
fi
RESULT_ZIP="$(find "$OUT_DIR" -name 'results.zip' | head -1 || true)"
if [ -n "$RESULT_ZIP" ]; then
  echo "   Extracting $(basename "$(dirname "$RESULT_ZIP")")/results.zip ..."
  (cd "$(dirname "$RESULT_ZIP")" && python3 -c "import zipfile; zipfile.ZipFile('results.zip').extractall('.')")
fi

# Highest completed round = max N over adapter_roundN dirs (fallback: adapter/
# which is train_round1.py's copy of the last round).
LAST_ROUND="$(find "$OUT_DIR" -type d -name 'adapter_round*' \
  | sed 's/.*adapter_round//' | grep -E '^[0-9]+$' | sort -n | tail -1 || true)"
if [ -z "$LAST_ROUND" ]; then
  echo "   (no adapter_roundN dirs — using adapter/ fallback)"
  LAST_ROUND=0
fi
echo "✅ Highest completed round: ${LAST_ROUND:-none}"

ADAPTER_SRC=""
if [ "$LAST_ROUND" != "0" ]; then
  ADAPTER_SRC="$(find "$OUT_DIR" -type d -name "adapter_round$LAST_ROUND" | head -1 || true)"
fi
if [ -z "$ADAPTER_SRC" ]; then
  ADAPTER_SRC="$(find "$OUT_DIR" -type d -name adapter | head -1 || true)"
fi
if [ -z "$ADAPTER_SRC" ] || { [ ! -f "$ADAPTER_SRC/adapter_config.json" ] || { [ ! -f "$ADAPTER_SRC/adapter_model.safetensors" ] && [ ! -f "$ADAPTER_SRC/adapter_model.bin" ]; }; }; then
  echo "❌ No usable adapter found in kernel output (results.zip missing or malformed)." >&2
  echo "   Check the Output tab: https://www.kaggle.com/code/$USERNAME/$WATCH_SLUG" >&2
  exit 1
fi
echo "✅ Adapter source: ${ADAPTER_SRC##*/}/  ($(ls "$ADAPTER_SRC" | tr '\n' ' '))"

# ─── 3b. Decide the next round to push ─────────────────────────────────────
NEXT=""
case "$LAST_ROUND" in
  1) NEXT="round2" ;;
  2) NEXT="rounds34" ;;
  3) NEXT="round4" ;;
  4) NEXT="" ;;  # all 4 rounds done
  0) echo "⚠️  Could not determine completed round — stopping (no next push)." >&2; exit 1 ;;
esac

if [ -z "$NEXT" ]; then
  echo "🎉 All 4 rounds complete! Nothing left to push."
  echo "   Adapter dataset: https://www.kaggle.com/datasets/$USERNAME/$ADAPTER_DS"
  rm -rf "$OUT_DIR"
  exit 0
fi

case "$NEXT" in
  round2)   NEXT_NB="train_round2_kaggle.ipynb";   NEXT_META="kernel-metadata-round2.json";   NEXT_SLUG="vaca-qlora-rounds-1-2" ;;
  rounds34) NEXT_NB="train_rounds34_kaggle.ipynb"; NEXT_META="kernel-metadata-rounds34.json"; NEXT_SLUG="vaca-qlora-rounds-3-4" ;;
  round4)   NEXT_NB="train_round4_kaggle.ipynb";   NEXT_META="kernel-metadata-round4.json";   NEXT_SLUG="vaca-qlora-rounds-3-4" ;;
esac
echo "🔜 Next round: $NEXT (kernel $NEXT_SLUG)"

# ─── 4. Upload adapter as a dataset version ────────────────────────────────
AD_DIR="$(mktemp -d)"
# Zip the adapter CONTENTS at the zip root so the resume kernel's
# `z.extractall(ad_dst)` lands adapter_config.json DIRECTLY in
# /kaggle/working/adapter (matching the --load-adapter path).
(cd "$ADAPTER_SRC" && zip -q -r "$AD_DIR/adapter.zip" .)
sed "s/__USERNAME__/$USERNAME/g; s/__TITLE__/VACA Rounds 1-2 Adapter/g" \
  "$KAGGLE_DIR/adapter-dataset-metadata.json" > "$AD_DIR/dataset-metadata.json"

echo "   Uploading adapter dataset $USERNAME/$ADAPTER_DS ..."
if timeout 180 kaggle datasets create -p "$AD_DIR" 2>&1 | tail -3; then
  :
else
  echo "   Dataset exists — updating version instead..."
  timeout 180 kaggle datasets version -p "$AD_DIR" -m "round-$LAST_ROUND adapter (auto from $WATCH_SLUG)" 2>&1 | tail -3
fi
rm -rf "$AD_DIR"

# ─── 4b. Wait for the adapter dataset to be READY ─────────────────────────
# A kernel push referencing a still-processing dataset silently drops the
# dataset source (hit this earlier with the main dataset). Poll until ready.
echo "   Waiting for adapter dataset to be ready..."
for i in $(seq 1 60); do
  DS_ST="$(status_word kaggle datasets status "$USERNAME/$ADAPTER_DS")"
  [ -z "$DS_ST" ] && DS_ST="unknown"
  echo "  [$(date +%H:%M:%S)] dataset status: $DS_ST"
  [ "$DS_ST" = "ready" ] && break
  [ "$i" = 60 ] && { echo "❌ Adapter dataset not ready after ~10 min." >&2; exit 1; }
  sleep 10
done
echo "✅ Adapter dataset ready."

# ─── 5. Push the next kernel (round N+1) ───────────────────────────────────
KERNEL_DIR="$(mktemp -d)"
cp "$KAGGLE_DIR/$NEXT_NB" "$KERNEL_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$NEXT_META" > "$KERNEL_DIR/kernel-metadata.json"

echo "🚀 Pushing kernel $USERNAME/$NEXT_SLUG (round $((LAST_ROUND + 1)) of 4, single-GPU)..."
# --accelerator NvidiaTeslaT4 is passed for metadata compatibility, but it has
# been OBSERVED to be ignored (2026-08-01: vaca-qlora-rounds-1-2 ran with
# CUDA:False + no DNS despite it) — the manual web-UI settings are the real fix.
timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
rm -rf "$KERNEL_DIR"

# ⚠️ API push IGNORES enable_internet/machine_shape (verified 2026-08-01:
# vaca-qlora-rounds-1-2 ran with CUDA:False + no DNS and errored in Step 1).
# The GPU + internet settings MUST be set by hand in the web UI.
echo ""
echo "⚠️⚠️⚠️  MANUAL STEP REQUIRED BEFORE RUNNING  ⚠️⚠️⚠️"
echo "  The API push ignores the GPU/internet settings in kernel-metadata.json"
echo "  (verified: kernels run with CUDA: False and no DNS). Set them by hand:"
echo ""
echo "    1. Open:  https://www.kaggle.com/code/$USERNAME/$NEXT_SLUG"
echo "    2. Click  Settings  (top right of the kernel editor)"
echo "    3. Accelerator → GPU T4 x2"
echo "    4. Internet    → ON"
echo "    5. Save, then click  Run All"
echo ""
echo "  Also confirm the adapter dataset is attached (Add Input → $ADAPTER_DS)"
echo "  Skipping this = kernel errors in Step 1 (no GPU, pip can't reach pypi)."
echo "⚠️⚠️⚠️  ─────────────────────────────────────────  ⚠️⚠️⚠️"
echo ""
echo "✅ Chain step complete!"
echo "   Watched kernel : https://www.kaggle.com/code/$USERNAME/$WATCH_SLUG (round $LAST_ROUND done)"
echo "   Next kernel    : https://www.kaggle.com/code/$USERNAME/$NEXT_SLUG (round $((LAST_ROUND + 1)))"
echo "   Adapter dataset: https://www.kaggle.com/datasets/$USERNAME/$ADAPTER_DS"
echo ""
echo "   All 4 rounds done when round 4 completes. Re-run this script with"
echo "   KERNEL_MODE=$NEXT to chain the following round automatically."
rm -rf "$OUT_DIR"
