#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Round-17 Kaggle dataset + kernel.
# =============================================================================
#   dataset : <user>/round17-corpus     (2,063 rows: R16 clean-code + ladder-r1
#                                        + round7-emotion + current verified)
#   kernel  : <user>/vaca-qlora-round17  (first Qwen2.5-Coder-14B round, fresh
#                                        base — NO resume adapter, single-GPU)
#
# Usage:
#   bash scripts/kaggle-setup-round17.sh                # dataset + kernel
#   bash scripts/kaggle-setup-round17.sh --skip-push    # dataset only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-round17.sh
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

DATASET_SLUG="round17-corpus"
KERNEL_SLUG="vaca-qlora-round17"
KERNEL_NB="train_r17_coder14_kaggle.ipynb"
KERNEL_META="kernel-metadata-round17.json"
DATASET_JSONL="$CLOUD_DIR/round17-train.jsonl"

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/build-r17-corpus.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-round17-kaggle-notebook.py" >&2; exit 1; }

# ─── 3. Dataset: round17-corpus ───────────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/"
# dataset-metadata.json uses __USERNAME__ placeholder; create it on the fly
cat > "$DATASET_DIR/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_SLUG",
  "title": "VACA Round-17 corpus (14B coder base)",
  "subtitle": "2063 rows: R16 clean-code + ladder-r1 verified + round7-emotion + verified",
  "licenses": [{ "name": "other" }]
}
EOF

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round-17 corpus (14B coder round)" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Kernel (needs the dataset ready — word-based check) ───────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
else
  READY=0
  for attempt in $(seq 1 30); do
    A_RDY=$(timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" 2>/dev/null | grep -c ready || true)
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

  KERNEL_DIR="$(mktemp -d)"
  cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
  sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

  PUSHED=0
  for attempt in $(seq 1 6); do
    echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (attempt $attempt) ..."
    OUT="$(timeout 240 kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 || true)"
    echo "$OUT" | tail -4
    if echo "$OUT" | grep -qi "successfully pushed"; then
      PUSHED=1
      break
    fi
    sleep 120
  done
  rm -rf "$KERNEL_DIR"

  if [ "$PUSHED" = "1" ]; then
    echo ""
    echo "   ✅ Kernel pushed. Live: https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  else
    echo "   ❌ Kernel push did not confirm after 6 attempts." >&2
    exit 1
  fi
fi

echo ""
echo "✅ Round-17 setup complete (dataset pushed; kernel pushed)."
