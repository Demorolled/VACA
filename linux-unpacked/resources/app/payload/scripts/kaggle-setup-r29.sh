#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-setup-r29.sh — push the R29 continue-training pack to Kaggle
# =============================================================================
#   dataset A: <user>/vaca-r29-corpus  (train/val.jsonl + corpus.json marker)
#   dataset B: <user>/vaca-r29-start   (R28 adapter pack + start.json)
#   dataset C: <user>/vaca-r29-resume  (placeholder; monitor versions with
#                                       in-training snapshots between segments)
#   kernel   : <user>/vaca-qlora-round29-r28-continue-26h  (26h budget)
#
# Usage:
#   bash scripts/kaggle-setup-r29.sh
#   bash scripts/kaggle-setup-r29.sh --skip-push     # datasets only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

SKIP_PUSH=0
if [ "${1:-}" = "--skip-push" ]; then SKIP_PUSH=1; fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KAGGLE_DIR="$ROOT/kaggle_kernel"
R29_DIR="$ROOT/training/cloud/round29"
R28_ADAPTER="$ROOT/training/cloud/out/round28-14b/final"

DATASET_CORPUS="vaca-r29-corpus"
DATASET_START="vaca-r29-start"
DATASET_RESUME="vaca-r29-resume"
KERNEL_SLUG="vaca-qlora-round29-r28-continue-26h"
KERNEL_NB="train_r29_kaggle.ipynb"
KERNEL_META="kernel-metadata-r29.json"

# ─── 1. Credentials ────────────────────────────────────────────────────────
USERNAME="$(python3 -c "import json;print(json.load(open('$HOME/.kaggle/credentials.json'))['username'])" 2>/dev/null || true)"
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username." >&2; exit 1
fi
echo "✅ Kaggle username: $USERNAME"
if ! timeout 30 python3 -m kaggle competitions list -p 1 >/dev/null 2>&1; then
  echo "❌ Kaggle API call failed — check credentials." >&2; exit 1
fi
echo "✅ API access OK"

# ─── 2. Preconditions: corpus + notebook ───────────────────────────────────
if [ ! -f "$R29_DIR/train.jsonl" ]; then
  echo "📦 Building R29 corpus (all untrained pools, deduped vs R28)..."
  python3 "$SCRIPT_DIR/build-r29-corpus.py"
fi
[ -f "$R29_DIR/train.jsonl" ] || { echo "❌ corpus build failed" >&2; exit 1; }
echo "   corpus: $(wc -l < "$R29_DIR/train.jsonl") train / $(wc -l < "$R29_DIR/val.jsonl") val"
[ -f "$R28_ADAPTER/adapter_config.json" ] || { echo "❌ R28 adapter not found at $R28_ADAPTER" >&2; exit 1; }

if [ ! -f "$KAGGLE_DIR/$KERNEL_NB" ]; then
  python3 "$SCRIPT_DIR/build-r29-kaggle-notebook.py"
fi

# ─── 3. Dataset A: corpus ──────────────────────────────────────────────────
d_create_version() {
  local dir="$1" id="$2" exists="$3"
  if [ "$exists" = "1" ]; then
    echo "   Dataset exists — pushing new version..."
    timeout 300 python3 -m kaggle datasets version -p "$dir" -m "Refresh" 2>&1 | tail -2
  else
    echo "   Creating dataset..."
    timeout 240 python3 -m kaggle datasets create -p "$dir" 2>&1 | tail -2
  fi
}

d_exists() { timeout 60 python3 -m kaggle datasets status "$USERNAME/$1" >/dev/null 2>&1 && echo 1 || echo 0; }

DIR_A="$(mktemp -d)"
cp "$R29_DIR/train.jsonl" "$R29_DIR/val.jsonl" "$R29_DIR/corpus.json" "$DIR_A/"
cat > "$DIR_A/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_CORPUS",
  "title": "VACA R29 continue corpus (26h round)",
  "subtitle": "All untrained pools: Sky-T1, R23/24, GUI, library, misc (dedup vs R28)",
  "licenses": [{ "name": "other" }]
}
EOF
echo "── Dataset A: $USERNAME/$DATASET_CORPUS ──"
d_create_version "$DIR_A" "$DATASET_CORPUS" "$(d_exists "$DATASET_CORPUS")"
rm -rf "$DIR_A"

# ─── 4. Dataset B: R28 start adapter ───────────────────────────────────────
DIR_B="$(mktemp -d)"
cp "$R28_ADAPTER/adapter_config.json" "$R28_ADAPTER/adapter_model.safetensors" "$DIR_B/"
echo '{"model": "r28", "round": 28, "note": "current VACA 14B — R29 continues from here"}' > "$DIR_B/start.json"
cat > "$DIR_B/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_START",
  "title": "VACA R29 start adapter (R28)",
  "subtitle": "R28 adapter - current VACA 14B, loaded to continue training",
  "licenses": [{ "name": "other" }]
}
EOF
echo "── Dataset B: $USERNAME/$DATASET_START ──"
d_create_version "$DIR_B" "$DATASET_START" "$(d_exists "$DATASET_START")"
rm -rf "$DIR_B"

# ─── 5. Dataset C: resume placeholder (only ever created here; the monitor
#       versions it with real snapshots between segments) ────────────────────
if [ "$(d_exists "$DATASET_RESUME")" != "1" ]; then
  DIR_C="$(mktemp -d)"
  echo '{"round": 29, "elapsed_h": 0.0, "segment": 0, "note": "placeholder — monitor versions this with real snapshots"}' > "$DIR_C/resume.json"
  cat > "$DIR_C/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_RESUME",
  "title": "VACA R29 resume state",
  "subtitle": "In-training adapter + resume.json to continue across sessions",
  "licenses": [{ "name": "other" }]
}
EOF
  echo "── Dataset C: $USERNAME/$DATASET_RESUME (create placeholder) ──"
  timeout 240 python3 -m kaggle datasets create -p "$DIR_C" 2>&1 | tail -2
  rm -rf "$DIR_C"
else
  echo "── Dataset C: $DATASET_RESUME already exists ──"
fi

# ─── 6. Wait for datasets to become ready ──────────────────────────────────
ready_wait() {
  for attempt in $(seq 1 30); do
    if timeout 60 python3 -m kaggle datasets status "$USERNAME/$1" 2>/dev/null | grep -q ready; then
      echo "   ✅ $1 ready"; return 0
    fi
    sleep 30
  done
  echo "   ❌ $1 still not ready after 15 min" >&2; return 1
}
ready_wait "$DATASET_CORPUS"
ready_wait "$DATASET_START"
ready_wait "$DATASET_RESUME"

if [ "$SKIP_PUSH" = "1" ]; then
  echo "   ⏭️  --skip-push set — notebook NOT pushed."
  exit 0
fi

# ─── 7. Push kernel ────────────────────────────────────────────────────────
KERNEL_DIR="$(mktemp -d)"
cp "$KAGGLE_DIR/$KERNEL_NB" "$KERNEL_DIR/"
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$KERNEL_META" > "$KERNEL_DIR/kernel-metadata.json"

PUSHED=0
for attempt in $(seq 1 6); do
  echo "   Pushing kernel $USERNAME/$KERNEL_SLUG (attempt $attempt) ..."
  OUT="$(timeout 300 python3 -m kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4 2>&1 || true)"
  echo "$OUT" | tail -4
  if echo "$OUT" | grep -qi "successfully pushed"; then PUSHED=1; break; fi
  sleep 120
done
rm -rf "$KERNEL_DIR"

if [ "$PUSHED" = "1" ]; then
  echo "   ✅ kernel pushed — $USERNAME/$KERNEL_SLUG"
  echo "   Next: bash scripts/kaggle-mon-r29.sh   (deep monitor + restart until 26h)"
else
  echo "   ❌ kernel push failed after 6 attempts" >&2
  exit 1
fi