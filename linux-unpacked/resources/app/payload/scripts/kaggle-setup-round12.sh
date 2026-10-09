#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Round-12 Defects Kaggle datasets + kernel (3D probe-failure fix)
# =============================================================================
#   dataset A : <user>/round12-defects    (defect-fix rows + 3D re-exposure
#                                          + round-11 retention slice)
#   dataset B : <user>/vaca-r11-adapter   (the REAL round-11 LoRA — e3b7e7cc,
#                                          staged at out/round11/adapter_trained)
#   kernel    : <user>/vaca-qlora-round12 (single-GPU, round 12, LR 5e-5,
#                                          3 epochs, grad-accum 4,
#                                          --load-adapter R11, --no-gguf)
#
# Usage:
#   bash scripts/kaggle-setup-round12.sh                # datasets + push kernel
#   bash scripts/kaggle-setup-round12.sh --skip-push    # datasets only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-round12.sh
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

DATASET_SLUG="round12-defects"
ADAPTER_SLUG="vaca-r11-adapter"
KERNEL_SLUG="vaca-qlora-round12"
KERNEL_NB="train_r12_defects_kaggle.ipynb"
KERNEL_META="kernel-metadata-round12.json"
DS_META="round12-defects-dataset-metadata.json"
ADAPTER_META="r11-adapter-dataset-metadata.json"
DATASET_JSONL="$CLOUD_DIR/round12-defects-train.jsonl"
ADAPTER_SRC="$CLOUD_DIR/out/round11/adapter_trained"   # REAL R11 LoRA (e3b7e7cc)
MERGED_SRC="$CLOUD_DIR/out/round11/merged"             # tokenizer files for dataset B

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/combine-defects-r12.py first" >&2; exit 1; }
[ -f "$ADAPTER_SRC/adapter_config.json" ] || { echo "❌ Missing $ADAPTER_SRC/adapter_config.json — the REAL R11 LoRA" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-r12-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset A: round12-defects (training rows) ─────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/round12-defects-train.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round-12 defect-fix rows" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Dataset B: vaca-r11-adapter (REAL round-11 trained LoRA) ───────────
ADAPTER_DIR="$(mktemp -d)"
cp "$ADAPTER_SRC"/adapter_config.json "$ADAPTER_SRC"/adapter_model.safetensors "$ADAPTER_DIR/" 2>/dev/null
# tokenizer files so the kernel can instantiate the full adapter
for tf in tokenizer.json tokenizer_config.json chat_template.jinja; do
  [ -f "$MERGED_SRC/$tf" ] && cp "$MERGED_SRC/$tf" "$ADAPTER_DIR/"
done
printf '# VACA R11 LoRA (real trained adapter, e3b7e7cc)\nResume point for round 12. Trained 26 optimizer steps on the round-11 Mix A (102 rows, LR 5e-5, seq 2048).\n' > "$ADAPTER_DIR/README.md"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$ADAPTER_META" > "$ADAPTER_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$ADAPTER_SLUG (REAL round-11 trained LoRA) ..."
if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$ADAPTER_DIR" -m "Refresh: real R11 trained LoRA adapter" 2>&1 | tail -3
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

  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (round 12, resume-R11, single-GPU) ..."
  timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 | tail -6
  rm -rf "$KERNEL_DIR"

  echo ""
  echo "   ✅ Kernel pushed. GPU (T4) + Internet are set via kernel-metadata.json"
  echo "      Live page: https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo "      Status:   kaggle kernels status $USERNAME/$KERNEL_SLUG"
fi

echo ""
echo "✅ Round-12 Defects Kaggle push complete (dataset A: data, dataset B: real R11 LoRA)."
echo "   Local R11 model unchanged — dspark still serves it on :8000 (will be backed up before R12 deploy)."
