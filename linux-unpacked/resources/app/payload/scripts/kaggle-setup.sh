#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push a VACA QLoRA round to Kaggle (dataset + notebook)
# =============================================================================
# Requirements:
#   1. kaggle CLI installed (pip install kaggle)
#   2. ~/.kaggle/kaggle.json with {"username": ..., "key": ...}
#      (create at https://www.kaggle.com/settings → API → Create New Token)
#
# What it does:
#   1. Verifies credentials + API access
#   2. Creates/versions the private dataset  <user>/vaca-campaign50-dataset
#   3. Pushes the SELECTED kernel mode (default rounds12 — round 1 fresh):
#        --kernel rounds12  → round 1 of 4 (LR 2e-4, fresh)   [vaca-qlora-rounds-1-2]
#        --kernel round2    → round 2 of 4 (LR 1e-4, resumes) [vaca-qlora-rounds-1-2]
#        --kernel rounds34  → round 3 of 4 (LR 5e-5, resumes) [vaca-qlora-rounds-3-4]
#        --kernel round4    → round 4 of 4 (LR 2.5e-5, resumes) [vaca-qlora-rounds-3-4]
#      Resume modes need the vaca-rounds12-adapter dataset attached (updated by
#      scripts/kaggle-watch-adapter.sh / kaggle-chain-rounds.sh).
#      ⚠️ The API push IGNORES the metadata GPU/internet flags — they must be set
#      manually in the web UI (Settings → Accelerator → GPU T4 x2, Internet → ON).
#   4. Prints a summary + (on push) the kernel URL and next steps
#
# Usage:
#   bash scripts/kaggle-setup.sh                 # dataset + push kernel 1 (round 1)
#   bash scripts/kaggle-setup.sh --kernel round2 # push the round-2 resume kernel
#   bash scripts/kaggle-setup.sh --skip-push     # dataset only — do NOT push
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SKIP_PUSH=0
KERNEL="rounds12"
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1 ;;
    --kernel) shift; KERNEL="${1:-rounds12}" ;;
    *) echo "❌ Unknown argument: $1 (expected --skip-push or --kernel rounds12|round2|rounds34|round4)" >&2; exit 1 ;;
  esac
  shift || true
done

# Map kernel mode → notebook file, metadata file, kernel slug, human label.
case "$KERNEL" in
  rounds12) KERNEL_NB="train_rounds12_kaggle.ipynb"; KERNEL_META="kernel-metadata-rounds12.json"; KERNEL_SLUG="vaca-qlora-rounds-1-2"; KERNEL_LABEL="round 1 of 4 (fresh, LR 2e-4)" ;;
  round2)   KERNEL_NB="train_round2_kaggle.ipynb";   KERNEL_META="kernel-metadata-round2.json";   KERNEL_SLUG="vaca-qlora-rounds-1-2"; KERNEL_LABEL="round 2 of 4 (resumes r1, LR 1e-4)" ;;
  rounds34) KERNEL_NB="train_rounds34_kaggle.ipynb"; KERNEL_META="kernel-metadata-rounds34.json"; KERNEL_SLUG="vaca-qlora-rounds-3-4"; KERNEL_LABEL="round 3 of 4 (resumes r2, LR 5e-5)" ;;
  round4)   KERNEL_NB="train_round4_kaggle.ipynb";   KERNEL_META="kernel-metadata-round4.json";   KERNEL_SLUG="vaca-qlora-rounds-3-4"; KERNEL_LABEL="round 4 of 4 (resumes r3, LR 2.5e-5)" ;;
  *) echo "❌ --kernel must be rounds12|round2|rounds34|round4 (got: $KERNEL)" >&2; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KAGGLE_DIR="$CLOUD_DIR/kaggle"

# ─── 1. Credentials ────────────────────────────────────────────────────────
# Auth works via EITHER ~/.kaggle/kaggle.json (username+key) OR
# ~/.kaggle/access_token (new-style KGAT_ token). Username is read from
# kaggle.json when present, else parsed from `kaggle config view`.
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found."
  echo "   Create a token at https://www.kaggle.com/settings → API → Create New Token"
  echo "   then either save the downloaded kaggle.json at: $KAGGLE_JSON"
  echo "   or store the KGAT_ token in: $HOME/.kaggle/access_token (chmod 600)"
  exit 1
fi

USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  # Fallback: parse username from kaggle config view output
  USERNAME="$(kaggle config view 2>/dev/null | grep -oP 'username: \K\S+' || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — either kaggle.json needs a username,"
  echo "   or the access_token-only setup needs it. Fix with:"
  echo "   KAGGLE_USERNAME=<name> bash scripts/kaggle-setup.sh"
  exit 1
fi
echo "✅ Kaggle username: $USERNAME"

echo "   Verifying API access..."
# competitions list is auth-gated and works in CLI 2.2.4 (kaggle api version does NOT exist there)
if ! timeout 30 kaggle competitions list -p 1 >/dev/null 2>&1; then
  echo "❌ Kaggle API call failed — check ~/.kaggle/kaggle.json or ~/.kaggle/access_token"
  exit 1
fi
echo "✅ API access OK"

# ─── 2. Dataset ────────────────────────────────────────────────────────────
[ -f "$CLOUD_DIR/campaign50-dataset.zip" ] || { echo "❌ Missing $CLOUD_DIR/campaign50-dataset.zip"; exit 1; }

DATASET_DIR="$(mktemp -d)"
cp "$CLOUD_DIR/campaign50-dataset.zip" "$DATASET_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/dataset-metadata.json" > "$DATASET_DIR/dataset-metadata.json"

echo "   Uploading dataset ${USERNAME}/vaca-campaign50-dataset ..."
# Decide create-vs-version by an EXPLICIT existence check, not by create's exit
# code: `kaggle datasets create` prints "Dataset creation error: ... already in use"
# but still exits 0 (observed 2026-08-01), so an `if create; then : else version`
# silently skips the update and the remote dataset never refreshes.
if timeout 60 kaggle datasets status "$USERNAME/vaca-campaign50-dataset" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  # -m/--message is REQUIRED by `kaggle datasets version` (CLI 2.2.4).
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: 4,122 rows (self-contained anti-delegation examples)" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  # datasets are PRIVATE by default in CLI 2.2.4 (-u/--public is the opt-in).
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

# ─── 3. Notebook (selected kernel mode) ───────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed (existing kernel left as-is)."
else
  KERNEL_DIR="$(mktemp -d)"
  cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
  sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

  echo "   Pushing kernel ${USERNAME}/$KERNEL_SLUG ($KERNEL_LABEL, single-GPU) ..."
  # NOTE: pushing with an existing id creates a NEW kernel version that QUEUES
  # AND RUNS on Kaggle — use --skip-push on re-runs to avoid burning GPU quota.
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
  echo "    1. Open:  https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo "    2. Click  Settings  (top right of the kernel editor)"
  echo "    3. Accelerator → GPU T4 x2"
  echo "    4. Internet    → ON"
  echo "    5. Save, then click  Run All"
  echo ""
  echo "  Skipping this = kernel errors in Step 1 (no GPU, pip can't reach pypi)."
  echo "⚠️⚠️⚠️  ─────────────────────────────────────────  ⚠️⚠️⚠️"
fi

# ─── 4. Done ───────────────────────────────────────────────────────────────
if [ "$SKIP_PUSH" = "1" ]; then
  echo ""
  echo "✅ Done (--skip-push): dataset updated, notebook NOT pushed."
  echo "   When ready to push a kernel, re-run without --skip-push:"
  echo "   bash scripts/kaggle-setup.sh [--kernel rounds12|round2|rounds34|round4]"
  echo "   (Then set Settings → Accelerator → GPU T4 x2 + Internet → ON in the web UI.)"
else
  echo ""
  echo "✅ Kaggle kernel pushed: $KERNEL_LABEL"
  echo "   Dataset : https://www.kaggle.com/datasets/$USERNAME/vaca-campaign50-dataset"
  echo "   Kernel  : https://www.kaggle.com/code/$USERNAME/$KERNEL_SLUG"
  echo ""
  echo "   Next steps:"
  echo "   1. Open the kernel, verify the dataset is attached (Add Input → vaca-campaign50-dataset)"
  if [ "$KERNEL" != "rounds12" ]; then
    echo "   1b. Resume modes need the adapter attached (Add Input → vaca-rounds12-adapter)"
  fi
  echo "   2. Settings → Accelerator → GPU T4 x2, Internet: ON  (MUST be set in the"
  echo "      web UI — the API push ignores the metadata GPU/internet settings)"
  echo "   3. ~6-10 h on 1×T4 (one round) → download /kaggle/working/out/results.zip from the Output tab"
  echo "   4. After this round completes: run scripts/kaggle-watch-adapter.sh to prepare"
  echo "      the next adapter zip, then push the next round (e.g. --kernel round2)."
fi
