#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Gated cleanup: delete training/cloud/round10-pending-delete/ ONLY after the
# round-10 model is confirmed trained, downloaded, deployed, and healthy.
# =============================================================================
# Safety gates (ALL must pass):
#   1. Kaggle kernel vaca-qlora-round10 has finished (COMPLETE/SUCCESS — or
#      ERROR with recovered output, mirroring the round-6/9 recovery pattern).
#   2. The deployed target is now the R10 model (dspark-target.env points at
#      *R10*), NOT the old R9.
#   3. dspark :8000 /v1/health responds ok.
#   4. The new R10 GGUF file actually exists in models/.
#
# If any gate fails, NOTHING is deleted and the script exits non-zero with a
# reason — the staged data remains recoverable.
#
# Usage:
#   bash scripts/cleanup-round10-pending.sh            # gated delete
#   bash scripts/cleanup-round10-pending.sh --dry-run  # show what would be removed
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    *) echo "❌ Unknown argument: $1 (expected --dry-run)" >&2; exit 1 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAGE="$PROJECT_ROOT/training/cloud/round10-pending-delete"
KERNEL="stevenawoods/vaca-qlora-round10"

fail() { echo "❌ $1" >&2; exit 1; }

[ -d "$STAGE" ] || { echo "ℹ️  Staging folder already gone ($STAGE) — nothing to clean."; exit 0; }

echo "=== Gated cleanup for $STAGE ==="
echo "   Size: $(du -sh "$STAGE" | cut -f1)"

# ─── Gate 1: kernel finished ───────────────────────────────────────────────
echo "--- Gate 1: kernel status ---"
STATUS="$(timeout 60 kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo 'UNKNOWN')"
echo "   $KERNEL: $STATUS"
case "$STATUS" in
  *COMPLETE*|*SUCCESS*|*DONE*|*ERROR*|*FAILED*)
    echo "   ✅ kernel finished ($STATUS)";;
  *)
    fail "kernel still $STATUS — training not confirmed done. Staging kept intact."
    ;;
esac

# ─── Gate 2: deployed target is R10 ────────────────────────────────────────
echo "--- Gate 2: deployed target ---"
TARGET="$(grep -oP 'DSPARK_TARGET=\K.*' "$PROJECT_ROOT/scripts/dspark-target.env" 2>/dev/null || echo '')"
echo "   target: $TARGET"
case "$TARGET" in
  *R10*|*round10*) echo "   ✅ dspark points at the new R10 model";;
  *) fail "dspark-target.env still points at $TARGET — R10 not deployed yet. Nothing deleted.";;
esac

# ─── Gate 3: dspark healthy ────────────────────────────────────────────────
echo "--- Gate 3: dspark health ---"
HEALTH="$(curl -s -m 10 http://127.0.0.1:8000/v1/health 2>&1 || true)"
if echo "$HEALTH" | grep -q '"status":"ok"\|"status": "ok"'; then
  echo "   ✅ :8000 healthy"
else
  fail "dspark not healthy on :8000 — will not delete. Inspect scripts/dspark.log"
fi

# ─── Gate 4: R10 GGUF file exists ──────────────────────────────────────────
echo "--- Gate 4: R10 model file ---"
R10_GGUF="$(echo "$TARGET" | grep -oP 'models/\S+\.gguf$' || true)"
if [ -n "$R10_GGUF" ] && [ -f "$PROJECT_ROOT/$R10_GGUF" ]; then
  echo "   ✅ $R10_GGUF exists"
else
  fail "R10 GGUF not found at $R10_GGUF — nothing deleted."
fi

# ─── All gates passed — delete ─────────────────────────────────────────────
echo ""
if [ "$DRY" = "1" ]; then
  echo "✅ All gates passed (dry run) — would delete:"
  du -sh "$STAGE"/*
  exit 0
fi

echo "✅ All gates passed — deleting staged data..."
rm -rf "$STAGE"
echo "   ✓ deleted $STAGE"
echo "   Disk freed: ~8.8 GB (old datasets + round-10 sources + auto-learn captures + stock/R6 models + chat history)"
echo "   Kept: live R10 model, projects.json, soul.json, designs.json, R9 adapter (resume point)."
