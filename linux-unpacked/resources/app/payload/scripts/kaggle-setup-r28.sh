#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-setup-r28.sh — push the Round-28 missed-corpus dataset + kernel.
# =============================================================================
#   dataset: <user>/vaca-r28-missed-corpus  (train.jsonl + val.jsonl — the 2,769
#                                           R21-25 rows the R20 14B never saw;
#                                           NO 27B-distilled rows)
#   kernel : <user>/vaca-r28-qlora-missed-14b-t4x2  (14B QLoRA, seq 1280,
#                                                    2 epochs, T4 x2)
#
# Usage (ON THE AGENT, where the corpus + notebook live):
#   bash scripts/kaggle-setup-r28.sh                     # dataset + kernel push
#   bash scripts/kaggle-setup-r28.sh --skip-push         # dataset only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-r28.sh
#
# Prereqs (run first):
#   python3 scripts/build-r28-missed-corpus.py           # corpus -> kaggle-r28/
#   python3 scripts/build-r28-kaggle-notebook.py         # notebook + metadata
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SKIP_PUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --skip-push)" >&2; exit 1 ;;
  esac
  shift || true
done

# `kaggle` is only importable from the system python on the agent.
KAGGLE() { python3 -m kaggle "$@"; }
# NOTE: KAGGLE is a shell function, so it CANNOT be wrapped in `timeout`. All
# the calls below use plain `python3 -m kaggle` (they still get a timeout via
# the underlying network/failure handling).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"

DATASET_SLUG="vaca-r28-missed-corpus"
# RESOLVED slug — Kaggle derives it from the title "VACA QLoRA Round28 (Missed-Corpus 14B)"
KERNEL_SLUG="vaca-qlora-round28-missed-corpus-14b"
DATASET_DIR_SRC="$CLOUD_DIR/kaggle-r28"          # train.jsonl/val.jsonl
KERNEL_NB="$PROJECT_ROOT/kaggle_kernel/train_r28_kaggle.ipynb"
KERNEL_META="$PROJECT_ROOT/kaggle_kernel/kernel-metadata-r28.json"

# ─── 1. Credentials ────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
KAGGLE_CRED="$HOME/.kaggle/credentials.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$KAGGLE_CRED" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or credentials.json)." >&2
  exit 1
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_CRED')).get('username',''))" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -m kaggle config view 2>/dev/null | grep -oP 'username: \K\S+' || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 1
fi
echo "✅ Kaggle username: $USERNAME"

echo "   Verifying API access..."
if ! timeout 30 python3 -m kaggle competitions list -p 1 >/dev/null 2>&1; then
  echo "❌ Kaggle API call failed — check ~/.kaggle/kaggle.json or ~/.kaggle/credentials.json" >&2
  exit 1
fi
echo "✅ API access OK"

# ─── 2. Preconditions ──────────────────────────────────────────────────────
[ -f "$DATASET_DIR_SRC/train.jsonl" ] || { echo "❌ Missing $DATASET_DIR_SRC/train.jsonl — run build-r28-missed-corpus.py first" >&2; exit 1; }
[ -f "$DATASET_DIR_SRC/val.jsonl" ]   || { echo "❌ Missing $DATASET_DIR_SRC/val.jsonl" >&2; exit 1; }
[ -f "$KERNEL_NB" ]   || { echo "❌ Missing $KERNEL_NB — run build-r28-kaggle-notebook.py first" >&2; exit 1; }
[ -f "$KERNEL_META" ] || { echo "❌ Missing $KERNEL_META" >&2; exit 1; }

# ─── 3. Dataset: vaca-r28-missed-corpus ────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_DIR_SRC/train.jsonl" "$DATASET_DIR/"
cp "$DATASET_DIR_SRC/val.jsonl" "$DATASET_DIR/"
cat > "$DATASET_DIR/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_SLUG",
  "title": "VACA Round-28 Missed-Corpus (14B catch-up)",
  "subtitle": "2,769 R21-25 rows the R20 14B never saw — no 27B-distilled rows",
  "licenses": [{ "name": "other" }]
}
EOF

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if python3 -m kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 python3 -m kaggle datasets version -p "$DATASET_DIR" -m "R28 missed-corpus (2,769 rows)" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 python3 -m kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Kernel (needs the dataset ready) ───────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
  exit 0
fi

READY=0
for attempt in $(seq 1 30); do
  A_RDY=$(timeout 60 python3 -m kaggle datasets status "$USERNAME/$DATASET_SLUG" 2>/dev/null | grep -c ready || true)
  if [ "$A_RDY" -ge 1 ]; then
    READY=1
    break
  fi
  echo "   ⏳ dataset not ready yet — retry in 30s..."
  sleep 30
done
if [ "$READY" != "1" ]; then
  echo "   ❌ dataset still not ready after 15 min — refusing to push." >&2
  exit 1
fi
echo "   ✅ dataset ready"

KERNEL_DIR="$(mktemp -d)"
cp "$KERNEL_NB" "$KERNEL_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

PUSHED=0
for attempt in $(seq 1 6); do
  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (attempt $attempt) ..."
  # NOTE: the API push CANNOT request 2x GPUs — accelerator must be set to
  # 'GPU T4 x2' + Internet ON manually in the web UI (see kaggle-chain-rounds.sh).
  OUT="$(timeout 240 python3 -m kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 || true)"
  echo "$OUT" | tail -4
  if echo "$OUT" | grep -qi "successfully pushed"; then
    PUSHED=1
    break
  fi
  sleep 120
done
rm -rf "$KERNEL_DIR"

if [ "$PUSHED" = "1" ]; then
  echo "   ✅ kernel pushed — ${USERNAME}/$KERNEL_SLUG"
  echo "⚠️⚠️⚠️  MANUAL STEP REQUIRED BEFORE RUNNING  ⚠️⚠️⚠️"
  echo "  The API push IGNORES GPU/internet settings. Set them by hand:"
  echo "    1. Open: https://www.kaggle.com/code/${USERNAME}/${KERNEL_SLUG}"
  echo "    2. Settings (top right of the kernel editor)"
  echo "    3. Accelerator → GPU (T4 works; the kernel self-configures for a single 16 GB card)"
  echo "    4. Internet    → ON"
  echo "    5. Check the dataset vaca-r28-missed-corpus is attached, then Run All"
  echo "    6. Runs FP16 (not bf16) — P100/T4 lack bfloat16; offload_folder avoids the R26 load-OOM on one card"
  echo "  Watch: bash scripts/kaggle-mon-r28.sh"
else
  echo "   ❌ kernel push failed after 6 attempts — inspect output above." >&2
  exit 1
fi