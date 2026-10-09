#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Round-13 Random-3D Kaggle datasets + kernel.
# =============================================================================
#   dataset A : <user>/round13-random    (12 NEW verified 3D apps + defects/3D
#                                         re-exposure + R12 retention slice)
#   dataset B : <user>/vaca-r12-adapter  (the R12 trained LoRA — chained;
#                                         uploaded AFTER R12 completes, by
#                                         scripts/kaggle-chain-r13.sh)
#   kernel    : <user>/vaca-qlora-round13 (single-GPU T4, seq 3072, 3 epochs,
#                                         grad-accum 4, resume R12)
#
# Usage:
#   bash scripts/kaggle-setup-round13.sh                # dataset A + push kernel
#   bash scripts/kaggle-setup-round13.sh --skip-push    # dataset A only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-round13.sh
#
# NOTE: the kernel push needs BOTH datasets ready. This script pushes dataset A
# and the kernel; if vaca-r12-adapter is not yet live it will warn. The chain
# script (kaggle-chain-r13.sh) re-pushes the kernel automatically once the R12
# adapter lands, so ordering is handled end-to-end.
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

DATASET_SLUG="round13-random"
ADAPTER_SLUG="vaca-r12-adapter"
KERNEL_SLUG="vaca-qlora-round13"
KERNEL_NB="train_r13_random_kaggle.ipynb"
KERNEL_META="kernel-metadata-round13.json"
DS_META="round13-random-dataset-metadata.json"
DATASET_JSONL="$CLOUD_DIR/round13-random-train.jsonl"

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/combine-random-r13.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-r13-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset A: round13-random (training rows) ─────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/round13-random-train.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round-13 random-3D rows" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Kernel (needs BOTH datasets — adapter may still be propagating) ────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
else
  if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" 2>/dev/null | grep -q ready; then
    KERNEL_DIR="$(mktemp -d)"
    cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
    sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

    echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (round 13, resume-R12, single-GPU) ..."
    timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
    rm -rf "$KERNEL_DIR"

    echo ""
    echo "   ✅ Kernel pushed. Live: https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  else
    echo "   ⚠️  $ADAPTER_SLUG not ready yet (R12 still training). Kernel push deferred."
    echo "      scripts/kaggle-chain-r13.sh will push it automatically after R12 completes."
  fi
fi

echo ""
echo "✅ Round-13 Random-3D setup complete (dataset A pushed; kernel gated on R12 adapter)."
