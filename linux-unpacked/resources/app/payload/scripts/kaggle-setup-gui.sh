#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the GUI-combined Kaggle dataset + kernel (combined GUI-design QLoRA)
# =============================================================================
#   dataset : <user>/gui-combined-all       (714 unique GUI rows)
#   kernel  : <user>/vaca-qlora-gui         (single-GPU, round 9, LR 5e-5)
#
# Usage:
#   bash scripts/kaggle-setup-gui.sh                # dataset + push kernel
#   bash scripts/kaggle-setup-gui.sh --skip-push    # dataset only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-gui.sh
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

DATASET_SLUG="gui-combined-all"
KERNEL_SLUG="vaca-qlora-gui"
KERNEL_NB="train_gui_kaggle.ipynb"
KERNEL_META="kernel-metadata-gui.json"
DS_META="gui-dataset-metadata.json"
DATASET_JSONL="$CLOUD_DIR/gui-combined-all.jsonl"

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/combine-gui-datasets.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-gui-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset ────────────────────────────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/gui-combined-all.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: combined GUI-design dataset" 2>&1 | tail -3
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

  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (GUI round, single-GPU) ..."
  timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
  rm -rf "$KERNEL_DIR"

  echo ""
  echo "   ✅ Kernel pushed. GPU (T4) + Internet are set via kernel-metadata.json"
  echo "      (verified for this round: kernel went RUNNING with CUDA available)."
  echo "      Live page: https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo "      Watchdog:  bash scripts/kaggle-watch-gui.sh"
fi

echo ""
echo "✅ GUI-combined Kaggle push complete."
