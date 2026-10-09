#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the ROUND-7 Kaggle dataset + kernel (Gemma-4 emotion distillation QLoRA)
# =============================================================================
# Same flow as kaggle-setup-r6.sh but for the round-7 artifacts:
#   dataset : <user>/round7-emotion       (round7-emotion.jsonl, ~1.1k rows)
#   kernel  : <user>/vaca-qlora-round7    (single-GPU, round 7, LR 5e-5)
#
# Usage:
#   bash scripts/kaggle-setup-r7.sh                # dataset + push kernel
#   bash scripts/kaggle-setup-r7.sh --skip-push    # dataset only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-r7.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SKIP_PUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --skip-push)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KAGGLE_DIR="$CLOUD_DIR/kaggle"

DATASET_SLUG="round7-emotion"
KERNEL_SLUG="vaca-qlora-round7"
KERNEL_NB="train_round7_kaggle.ipynb"
KERNEL_META="kernel-metadata-round7.json"
DS_META="round7-dataset-metadata.json"
DATASET_JSONL="$PROJECT_ROOT/training/dataset/round7-emotion.jsonl"

# ─── 1. Credentials ────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or access_token)." >&2
  exit 1
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  USERNAME="$(kaggle config view 2>/dev/null | grep -oP 'username: \K\S+' || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 1
fi
echo "✅ Kaggle username: $USERNAME"

echo "   Verifying API access..."
if ! timeout 30 kaggle competitions list -p 1 >/dev/null 2>&1; then
  echo "❌ Kaggle API call failed — check ~/.kaggle/kaggle.json or ~/.kaggle/access_token" >&2
  exit 1
fi
echo "✅ API access OK"

# ─── 2. Preconditions ──────────────────────────────────────────────────────
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/build-round7-emotion-dataset.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-r7-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset ────────────────────────────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/round7-emotion.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round7-emotion.jsonl (Gemma-4 emotion distillation)" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Notebook ───────────────────────────────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
else
  KERNEL_DIR="$(mktemp -d)"
  cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
  sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (round 7, single-GPU) ..."
  timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
  rm -rf "$KERNEL_DIR"

  echo ""
  echo "⚠️⚠️⚠️  MANUAL STEP REQUIRED BEFORE RUNNING  ⚠️⚠️⚠️"
  echo "  The API push ignores the GPU/internet settings in kernel-metadata.json"
  echo "  (verified: kernels run with CUDA: False and no DNS). Set them by hand:"
  echo ""
  echo "    1. Open:  https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo "    2. Click  Settings  (top right of the kernel editor)"
  echo "    3. Accelerator → GPU T4 x2"
  echo "    4. Internet    → ON"
  echo "    5. Save, then click  Run All"
  echo ""
  echo "⚠️⚠️⚠️  ─────────────────────────────────────────  ⚠️⚠️⚠️"
fi

echo ""
echo "✅ Round-7 Kaggle push complete."
