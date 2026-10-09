#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Sky-T1 SFT corpus + kernel to Kaggle (14B SFT reasoning round).
# =============================================================================
#   dataset A: <user>/vaca-sky1-sft-corpus   (train.jsonl/val.jsonl — converted
#                                            Sky-T1 reasoning rows)
#   kernel   : <user>/vaca-qlora-round-sky1  (Qwen2.5-Coder-14B SFT via
#                                            train_sky1_kaggle.py in the kernel)
#
# Usage:
#   bash scripts/kaggle-setup-sky1.sh                  # corpus + kernel
#   bash scripts/kaggle-setup-sky1.sh --skip-push      # corpus dataset only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-sky1.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Kaggle CLI lives at ~/.local/bin on this host and isn't on non-interactive PATH.
export PATH="$HOME/.local/bin:$PATH"

SKIP_PUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --skip-push)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KAGGLE_DIR="$ROOT/kaggle_kernel"
SKY_DIR="$ROOT/training/cloud/sky1"

DATASET_SLUG="vaca-sky1-sft-corpus"
KERNEL_SLUG="vaca-qlora-round-sky1"
KERNEL_NB="train_sky1_kaggle.ipynb"
KERNEL_META="kernel-metadata-sky1.json"

# ─── 1. Credentials ────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/credentials.json" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or credentials.json)." >&2
  exit 1
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ] && [ -f "$KAGGLE_JSON" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ] && [ -f "$HOME/.kaggle/credentials.json" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$HOME/.kaggle/credentials.json'))['username'])" 2>/dev/null || true)"
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
  echo "❌ Kaggle API call failed — check credentials." >&2
  exit 1
fi
echo "✅ API access OK"

# ─── 2. Preconditions ──────────────────────────────────────────────────────
[ -f "$SKY_DIR/train.jsonl" ] || { echo "❌ Missing $SKY_DIR/train.jsonl — run scripts/build-sky1-sft-corpus.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Missing $KAGGLE_DIR/$KERNEL_NB — run scripts/build-round-sky1-kaggle-notebook.py first" >&2; exit 1; }

# ─── 3. Dataset: vaca-sky1-sft-corpus ──────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$SKY_DIR/train.jsonl" "$SKY_DIR/val.jsonl" "$DATASET_DIR/"
cat > "$DATASET_DIR/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_SLUG",
  "title": "VACA Sky-T1 SFT corpus (14B reasoning)",
  "subtitle": "VACA Sky-T1 reasoning rows, instruction/input/output for SFT",
  "licenses": [{ "name": "other" }]
}
EOF

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: Sky-T1 SFT corpus" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Kernel ─────────────────────────────────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
  exit 0
fi

# Fill the username into kernel metadata.
META="$KAGGLE_DIR/$KERNEL_META"
sed "s/__USERNAME__/$USERNAME/g" "$META" > "$META.tmp" && mv "$META.tmp" "$META"

# ─── Wait for dataset ready ──────────────────────────────────────────────
READY=0
for attempt in $(seq 1 30); do
  A_RDY=$(timeout 60 python3 -m kaggle datasets status "$USERNAME/$DATASET_SLUG" 2>/dev/null | grep -c ready || true)
  if [ "$A_RDY" -ge 1 ]; then READY=1; break; fi
  echo "   ⏳ dataset not ready yet — retry in 30s..."
  sleep 30
done
if [ "$READY" != "1" ]; then
  echo "   ❌ dataset still not ready after 15 min — refusing to push kernel." >&2
  exit 1
fi
echo "   ✅ dataset ready"

# ─── Push kernel (R28-proven: module invoke + clean temp dir + accelerator) ──
KERNEL_DIR="$(mktemp -d)"
cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

PUSHED=0
for attempt in $(seq 1 6); do
  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (attempt $attempt) ..."
  OUT="$(timeout 240 python3 -m kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 || true)"
  echo "$OUT" | tail -4
  if echo "$OUT" | grep -qi "successfully pushed"; then PUSHED=1; break; fi
  sleep 120
done
rm -rf "$KERNEL_DIR"

if [ "$PUSHED" = "1" ]; then
  echo "   ✅ kernel pushed — ${USERNAME}/$KERNEL_SLUG"
  echo "⚠️⚠️⚠️  MANUAL STEP BEFORE RUNNING  ⚠️⚠️⚠️"
  echo "  The API push IGNORES GPU/internet. Set by hand in the kernel editor:"
  echo "    1. Open:  https://www.kaggle.com/code/${USERNAME}/${KERNEL_SLUG}"
  echo "    2. Settings (top right) → Accelerator → GPU (T4), Internet → ON"
  echo "    3. Confirm dataset vaca-sky1-sft-corpus attached, then Run All"
else
  echo "   ❌ kernel push failed after 6 attempts — inspect output above." >&2
  exit 1
fi