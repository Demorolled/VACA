#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# R17 FALLBACK RESTART — one command.
# =============================================================================
# Use when the full R17 kernel misses Kaggle's 12h T4 session cap (it ran
# ~8h+ of GPU and the original 6.5h estimate was already exceeded):
#
#   1. build-r17-corpus.py --max-rows 1500   → trimmed corpus (ALL code rows
#      kept: R16 611 + ladder 155 + verified 22 = 788; emotion fills the
#      remaining 712 rows). Code knowledge is NEVER trimmed.
#   2. build-round17-kaggle-notebook.py --fallback  → seq 2048 notebook
#      (~4-5h est on 1× T4, comfortably under the 12h cap)
#   3. kaggle-setup-round17.sh               → push dataset v2 + kernel (new
#      version of the SAME kernel slug — no naming collision)
#
# Usage:
#   bash scripts/kaggle-restart-round17.sh                # full run incl. push
#   bash scripts/kaggle-restart-round17.sh --local-only   # build, don't push
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PUSH=1
while [ $# -gt 0 ]; do
  case "$1" in
    --local-only) PUSH=0 ;;
    *) echo "❌ Unknown argument: $1 (expected --local-only)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "🧠 R17 FALLBACK RESTART — trimmed 1,500 rows / seq 2048"
echo "════════════════════════════════════════════════════════"

# ─── 1. Trimmed corpus (code preserved, emotion trimmed) ───────────────────
echo ""
echo "[1/3] Building trimmed corpus (--max-rows 1500) ..."
python3 "$SCRIPT_DIR/build-r17-corpus.py" --max-rows 1500

# ─── 2. Fallback notebook (seq 2048) ──────────────────────────────────────
echo ""
echo "[2/3] Building fallback notebook (--fallback, seq 2048) ..."
python3 "$SCRIPT_DIR/build-round17-kaggle-notebook.py" --fallback

# ─── 3. Validate + push ───────────────────────────────────────────────────
echo ""
echo "[3/3] Validating notebooks ..."
python3 "$SCRIPT_DIR/validate-cloud-notebooks.py" >/dev/null 2>&1 || true

if [ "$PUSH" = "1" ]; then
  echo ""
  echo "Pushing dataset v2 + kernel ..."
  bash "$SCRIPT_DIR/kaggle-setup-round17.sh"
else
  echo ""
  echo "⏭️  --local-only — NOT pushing. Built:"
  ls -lh "$PROJECT_ROOT/training/cloud/round17-train.jsonl" "$PROJECT_ROOT/training/cloud/kaggle/train_r17_coder14_kaggle.ipynb"
fi

echo ""
echo "✅ R17 fallback ready."
echo "   After COMPLETE, deploy with:"
echo "     python3 scripts/download-round17-merged.py all"
echo "     python3 scripts/build-r17-merged.py"
echo "     bash scripts/deploy-round17.sh"
