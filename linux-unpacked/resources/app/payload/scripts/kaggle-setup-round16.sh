#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Round-16 Anti-Fence Kaggle datasets + kernel.
# =============================================================================
#   dataset A : <user>/round16-antifence  (clean-only corpus — every row's
#                                          output passes the VACA isQualityCode
#                                          gate; 552 train / 61 val rows)
#   dataset B : <user>/vaca-r15-adapter   (the R15 trained LoRA — chained;
#                                          uploaded from the LOCAL R15 adapter
#                                          at training/cloud/out/round15/adapter)
#   kernel    : <user>/vaca-qlora-round16 (single-GPU T4, seq 3072, 3 epochs,
#                                          grad-accum 4, resume R15)
#
# Usage:
#   bash scripts/kaggle-setup-round16.sh                # datasets A+B + push kernel
#   bash scripts/kaggle-setup-round16.sh --skip-push    # datasets only
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-round16.sh
#
# NOTE: the kernel push needs BOTH datasets ready (word-based `grep -q ready`,
# not exit-code — the round-12 v1 race). Retries the push up to 6× with 2-min
# backoff until confirmed, then reports the kernel URL.
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

DATASET_SLUG="round16-antifence"
ADAPTER_SLUG="vaca-r15-adapter"
KERNEL_SLUG="vaca-r16-anti-fence-clean-round-resume-r15"
KERNEL_NB="train_r16_antifence_kaggle.ipynb"
KERNEL_META="kernel-metadata-round16.json"
DS_META="round16-antifence-dataset-metadata.json"
ADAPTER_META="r15-adapter-dataset-metadata.json"
DATASET_JSONL="$CLOUD_DIR/round16-antifence-train.jsonl"
ADAPTER_LOCAL="$CLOUD_DIR/out/round15/adapter"

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
[ -f "$DATASET_JSONL" ] || { echo "❌ Missing $DATASET_JSONL — run scripts/build-r16-antifence-corpus.py first" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$KERNEL_NB" ] || { echo "❌ Run the builder first: python3 scripts/build-round16-kaggle-notebook.py" >&2; exit 1; }
[ -f "$ADAPTER_LOCAL/adapter_model.safetensors" ] || { echo "❌ R15 adapter not on disk at $ADAPTER_LOCAL — deploy R15 first" >&2; exit 1; }

# ─── 3. Dataset A: round16-antifence (clean training rows) ─────────────────
DATASET_DIR="$(mktemp -d)"
cp "$DATASET_JSONL" "$DATASET_DIR/round16-antifence-train.jsonl"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: round-16 clean anti-fence rows" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 4. Dataset B: vaca-r15-adapter (local R15 trained LoRA) ──────────────
ADAPTER_DIR="$(mktemp -d)"
cp "$ADAPTER_LOCAL"/* "$ADAPTER_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$ADAPTER_META" > "$ADAPTER_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/$ADAPTER_SLUG (R15 trained LoRA)..."
if timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" >/dev/null 2>&1; then
  timeout 240 kaggle datasets version -p "$ADAPTER_DIR" -m "Refresh: R15 trained LoRA (gui-vision round)" 2>&1 | tail -3
else
  timeout 180 kaggle datasets create -p "$ADAPTER_DIR" 2>&1 | tail -3
fi
rm -rf "$ADAPTER_DIR"

# ─── 5. Kernel (needs BOTH datasets ready — word-based check) ─────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
else
  READY=0
  for attempt in $(seq 1 30); do
    A_RDY=$(timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" 2>/dev/null | grep -c ready || true)
    B_RDY=$(timeout 60 kaggle datasets status "$USERNAME/$ADAPTER_SLUG" 2>/dev/null | grep -c ready || true)
    if [ "$A_RDY" -ge 1 ] && [ "$B_RDY" -ge 1 ]; then
      READY=1
      break
    fi
    echo "   ⏳ datasets not ready yet (A=$A_RDY B=$B_RDY) — retry in 30s..."
    sleep 30
  done
  if [ "$READY" != "1" ]; then
    echo "   ❌ datasets still not ready after 15 min — refusing to push (avoids the R12-v1 'not a valid dataset source' race)." >&2
    exit 1
  fi

  KERNEL_DIR="$(mktemp -d)"
  cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
  sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

  PUSHED=0
  for attempt in $(seq 1 6); do
    echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG (round 16, resume-R15, single-GPU) — attempt $attempt ..."
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
echo "✅ Round-16 anti-fence setup complete (datasets A+B pushed; kernel pushed)."
