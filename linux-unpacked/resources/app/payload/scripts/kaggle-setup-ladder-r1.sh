#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push the Build-Ladder R1 dataset to Kaggle.
# =============================================================================
#   dataset : <user>/vaca-ladder-r1
#             - ladder-r1-train.jsonl   (103 verified module files, the same
#                                        {instruction,input,output,source}
#                                        format as the canonical train sets)
#             - ladder-r1-meta.jsonl    (per-build verdicts: pass/fail, errors,
#                                        duration, tier, smoke, file errors)
#             - build-improvement-report.md (speed/knowledge/complexity findings)
#             - build-ladder-results.jsonl (full raw records, when present)
#
# Usage:
#   bash scripts/kaggle-setup-ladder-r1.sh                # create or refresh dataset
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-setup-ladder-r1.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KAGGLE_DIR="$CLOUD_DIR/kaggle"

DATASET_SLUG="vaca-ladder-r1"
DS_META="ladder-r1-dataset-metadata.json"
TRAIN_JSONL="$CLOUD_DIR/ladder-r1-train.jsonl"
META_JSONL="$CLOUD_DIR/ladder-r1-meta.jsonl"
REPORT_MD="$PROJECT_ROOT/data/build-improvement-report.md"
RAW_RESULTS="$PROJECT_ROOT/data/build-ladder-results.jsonl"

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
[ -f "$TRAIN_JSONL" ] || { echo "❌ Missing $TRAIN_JSONL — run the datasheet builder first" >&2; exit 1; }
[ -f "$REPORT_MD" ] || { echo "❌ Missing $REPORT_MD" >&2; exit 1; }
[ -f "$KAGGLE_DIR/$DS_META" ] || { echo "❌ Missing $KAGGLE_DIR/$DS_META" >&2; exit 1; }

# ─── 3. Stage + push the dataset ───────────────────────────────────────────
DATASET_DIR="$(mktemp -d)"
cp "$TRAIN_JSONL" "$DATASET_DIR/"
cp "$META_JSONL" "$DATASET_DIR/"
cp "$REPORT_MD" "$DATASET_DIR/"
if [ -f "$RAW_RESULTS" ]; then
  cp "$RAW_RESULTS" "$DATASET_DIR/"
fi
sed "s/__USERNAME__/$USERNAME/g" "$KAGGLE_DIR/$DS_META" > "$DATASET_DIR/dataset-metadata.json"

echo "   Staged $(ls "$DATASET_DIR" | wc -l) files:"
ls -lh "$DATASET_DIR" | awk '{print "     " $5 "  " $9}'

echo "   Uploading dataset ${USERNAME}/$DATASET_SLUG ..."
if timeout 60 kaggle datasets status "$USERNAME/$DATASET_SLUG" >/dev/null 2>&1; then
  echo "   Dataset exists — pushing new version..."
  timeout 240 kaggle datasets version -p "$DATASET_DIR" -m "Refresh: ladder-r1 build data (verified module files + report)" 2>&1 | tail -3
else
  echo "   Dataset does not exist — creating..."
  timeout 180 kaggle datasets create -p "$DATASET_DIR" 2>&1 | tail -3
fi
rm -rf "$DATASET_DIR"

echo ""
echo "✅ Ladder-R1 dataset pushed. https://www.kaggle.com/datasets/$USERNAME/$DATASET_SLUG"
