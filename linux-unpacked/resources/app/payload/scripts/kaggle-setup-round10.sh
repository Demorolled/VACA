#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Round-10 Kaggle datasets + kernel (untrained catch-up, resume R9)
# =============================================================================
#   dataset A : <user>/round10-untrained     (1,109 unique untrained rows)
#   dataset B : <user>/vaca-r9-adapter       (trainable copy of the LIVE R9 model)
#   kernel    : <user>/vaca-qlora-round10    (single-GPU, round 10, LR 5e-5,
#                                             --load-adapter R9, --no-gguf)
#
# The local R9 model stays untouched and connected to the VACA app — dataset B
# is a COPY of its LoRA adapter, not a move.
#
# Usage:
#   bash scripts/kaggle-setup-round10.sh                # datasets + push kernel
#   bash scripts/kaggle-setup-round10.sh --skip-push    # datasets only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-round10.sh
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

DATASET_SLUG="round10-untrained"
ADAPTER_SLUG="vaca-r9-adapter"
KERNEL_SLUG="vaca-qlora-round10"
KERNEL_NB="train_round10_kaggle.ipynb"
KERNEL_META="kernel-metadata-round10.json"
DS_META="round10-dataset-metadata.json"
ADAPTER_META="r9-adapter-dataset-metadata.json"
DATASET_JSONL="$CLOUD_DIR/round10-train.jsonl"
ADAPTER_SRC="$CLOUD_DIR/out/gui-round/adapter"

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/combine-untrained-round10.py first" >&2; exit 1; }
[ -f "$ADAPTER_SRC/adapter_config.json" ] || { echo "❌ Missing $ADAPTER_SRC/adapter_config.json — the R9 adapter copy" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-round10-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset A: round10-untrained (training rows) ───────────────────────
DATASET_DIR="$(mktemp -d)"
# Single train file only — train_round1.py splits 10% internally (seed 42).
# The local round10-val.jsonl stays for offline evaluation, not uploaded.
cp "$DATASET_JSONL" "$DATASET_DIR/round10-train.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round-10 untrained catch-up dataset" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Dataset B: vaca-r9-adapter (trainable copy of the LIVE model) ──────
ADAPTER_DIR="$(mktemp -d)"
cp -r "$ADAPTER_SRC/." "$ADAPTER_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$ADAPTER_META" > "$ADAPTER_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$ADAPTER_SLUG (copy of live R9 LoRA — local copy stays connected) ..."
if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$ADAPTER_DIR" -m "Refresh: live R9 LoRA adapter" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$ADAPTER_DIR" 2>&1 | tail -3
fi
rm -rf "$ADAPTER_DIR"

# ─── 5. Notebook ───────────────────────────────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
else
  KERNEL_DIR="$(mktemp -d)"
  cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
  sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (round 10, resume-R9, single-GPU) ..."
  timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
  rm -rf "$KERNEL_DIR"

  echo ""
  echo "   ✅ Kernel pushed. GPU (T4) + Internet are set via kernel-metadata.json"
  echo "      Live page: https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo "      Status:   kaggle kernels status $USERNAME/$KERNEL_SLUG"
fi

echo ""
echo "✅ Round-10 Kaggle push complete (dataset A: data, dataset B: live R9 adapter copy)."
echo "   Local R9 model unchanged — dspark still serves it on :8000."
