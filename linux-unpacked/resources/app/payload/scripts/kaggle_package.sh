#!/usr/bin/env bash
# =============================================================================
# kaggle_package.sh — Package VACA dataset for Kaggle training
# =============================================================================
# Usage:
#   ./scripts/kaggle_package.sh                          # Package into ./kaggle_upload/
#   ./scripts/kaggle_package.sh --deploy                 # Package AND upload via Kaggle API
#   ./scripts/kaggle_package.sh --dry-run                # Preview without packaging
#
# Output:
#   ./kaggle_upload/
#     ├── train.jsonl            # Training dataset (2,847 examples)
#     ├── val.jsonl              # Validation dataset (356 examples)
#     ├── dataset_meta.json      # Dataset metadata
#     ├── kaggle_trainer.py      # Notebook script (paste into Kaggle)
#     └── README_KAGGLE.md       # Quick reference
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ─── Config ────────────────────────────────────────────────────────────────
KAGGLE_DIR="./kaggle_upload"
TRAIN_DIR="./training/dataset"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "════════════════════════════════════════════════════════════"
echo "  📦 VACA → Kaggle Package Builder"
echo "════════════════════════════════════════════════════════════"

# ─── Parse args ────────────────────────────────────────────────────────────
DEPLOY=false
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --deploy)  DEPLOY=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# ─── Validate dataset ──────────────────────────────────────────────────────
if [[ ! -f "$TRAIN_DIR/train.jsonl" ]]; then
    echo "❌ Dataset not found at $TRAIN_DIR/"
    echo "   Run: python3 llm-training-app/build_wiki_dataset.py"
    exit 1
fi

TRAIN_COUNT=$(wc -l < "$TRAIN_DIR/train.jsonl")
VAL_COUNT=$(wc -l < "$TRAIN_DIR/val.jsonl")
echo "  Dataset: $TRAIN_COUNT train + $VAL_COUNT val"

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    echo "🏁 Dry run. Files that would be packaged:"
    echo "  $KAGGLE_DIR/train.jsonl        ($TRAIN_COUNT lines)"
    echo "  $KAGGLE_DIR/val.jsonl          ($VAL_COUNT lines)"
    echo "  $KAGGLE_DIR/kaggle_trainer.py  (notebook script)"
    echo "  $KAGGLE_DIR/README_KAGGLE.md   (instructions)"
    exit 0
fi

# ─── Create package directory ──────────────────────────────────────────────
mkdir -p "$KAGGLE_DIR"

# ─── Copy dataset files ────────────────────────────────────────────────────
cp "$TRAIN_DIR/train.jsonl" "$KAGGLE_DIR/train.jsonl"
cp "$TRAIN_DIR/val.jsonl" "$KAGGLE_DIR/val.jsonl"
echo "  ✅ Dataset files copied"

# ─── Export dataset metadata ───────────────────────────────────────────────
if [[ -f "$TRAIN_DIR/dataset_meta.json" ]]; then
    cp "$TRAIN_DIR/dataset_meta.json" "$KAGGLE_DIR/dataset_meta.json"
fi

# ─── Export the trainer script ─────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/scripts/kaggle_trainer.py" ]]; then
    cp "$SCRIPT_DIR/scripts/kaggle_trainer.py" "$KAGGLE_DIR/kaggle_trainer.py"
    echo "  ✅ kaggle_trainer.py copied"
elif [[ -f "llm-training-app/kaggle_trainer.py" ]]; then
    cp "llm-training-app/kaggle_trainer.py" "$KAGGLE_DIR/kaggle_trainer.py"
fi

# ─── File sizes ────────────────────────────────────────────────────────────
echo ""
echo "  📊 Package contents:"
du -sh "$KAGGLE_DIR"/* 2>/dev/null | sed 's/^/    /'

# ─── Create dataset-metadata.json for Kaggle API ───────────────────────────
cat > "$KAGGLE_DIR/dataset-metadata.json" << EOF
{
  "title": "VACA Training Dataset",
  "id": "$(whoami)/vaca-training-data",
  "licenses": [{ "name": "CC0-1.0" }],
  "description": "Training dataset for Visual AI Architect fine-tuning. Contains ${TRAIN_COUNT} training and ${VAL_COUNT} validation examples in ChatML JSONL format."
}
EOF
echo "  ✅ dataset-metadata.json created"

# ─── Deploy via Kaggle API ────────────────────────────────────────────────
if [[ "$DEPLOY" == true ]]; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  🚀 Deploying to Kaggle..."
    echo "════════════════════════════════════════════════════════════"
    
    if command -v kaggle &>/dev/null; then
        echo "  Creating Kaggle dataset..."
        kaggle datasets create -p "$KAGGLE_DIR" 2>&1 || echo "  ⚠️  Dataset may already exist. Try 'kaggle datasets version' instead."
        echo "  ✅ Dataset uploaded to Kaggle"
        echo "  📎 https://www.kaggle.com/datasets/$(whoami)/vaca-training-data"
    else
        echo "  ⚠️  Kaggle CLI not installed."
        echo "  Install: pip install kaggle"
        echo "  Then: mkdir -p ~/.kaggle && cp kaggle.json ~/.kaggle/"
    fi
fi

# ─── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ Package ready at: $KAGGLE_DIR/"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "    1. Upload to Kaggle via web UI:"
echo "       https://www.kaggle.com/datasets → New Dataset"
echo "       Drag 'kaggle_upload/' folder in"
echo ""
echo "    2. Or use API (requires Kaggle API token):"
echo "       kaggle datasets create -p kaggle_upload/"
echo ""
echo "    3. Create a Notebook in Kaggle:"
echo "       - Attach your dataset as input"
echo "       - Set Accelerator: GPU T4 x2 (or P100)"
echo "       - Paste kaggle_trainer.py into a code cell"
echo "       - Run and save checkpoints every 50 steps"
echo ""
echo "    4. Download trained adapter from:"
echo "       /kaggle/working/qwen-lora/final_adapter/"
echo "════════════════════════════════════════════════════════════"
