#!/usr/bin/env bash
# check-training.sh — build-time validation gate for the VACA training pipeline
# =============================================================================
# Run on every training-pipeline build (wired into package.json "build" and
# the Makefile "check-training" target). Verifies:
#   1. py_compile of every pipeline Python script (syntax gate)
#   2. tsc_check concurrency safety (tests/test-tsc-concurrency.py) — guards
#      the unique-scratch-dir fix; fails if tsc_check regresses to the old
#      shared data/ab-test/tsc-tmp clobbering behaviour.
#   3. Probe self-check (tests/test-tsc-concurrency.py --fail-on-probe-clean)
#      — re-runs the shared-scratch regression probe and FAILS CI if it
#      produces zero spurious failures across --probe-rounds (default 3),
#      i.e. the probe no longer detects the bug it guards.
#   4. Notebook embedded-file sync (scripts/sync-notebook-embedded-files.py
#      --check) — fails if a notebook's %%writefile body has drifted from its
#      repo source, printing the one-line fix to re-embed it.
#   5. Cloud-notebook cell validation (scripts/validate-cloud-notebooks.py)
#      — compile-checks every code cell of the Colab + Kaggle notebooks so
#      escaping/typo bugs (e.g. the 2026-08-01 'Colab's' SyntaxError that
#      killed Step 2) and stale embedded trainers can never ship again.
#
# Skips (exit 0) when tsc isn't available (TSC_BIN missing) — the concurrency
# tests report "tsc not available — concurrency test skipped" themselves.
#
# Usage:
#   bash scripts/check-training.sh                 # full check (CI)
#   bash scripts/check-training.sh --quick         # fewer calls (fast local)
#   bash scripts/check-training.sh --skip-tsc-test # py_compile + notebook validation only

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

PY_SCRIPTS=(
  scripts/ab-test-tuned-vs-stock.py
  scripts/build-self-contained-corrected.py
  scripts/build-colab-dataset-zip.py
  scripts/build-kaggle-notebook.py
  scripts/build-vaca-knowledge-dataset.py
  scripts/merge-campaign50-into-dataset.py
  scripts/restore-dataset-meta.py
  scripts/validate-cloud-notebooks.py
  scripts/sync-notebook-embedded-files.py
  tests/test-kaggle-adaptive-run-cell.py
  tests/test-tsc-concurrency.py
)

QUICK=0
SKIP_TSC=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --skip-tsc-test) SKIP_TSC=1 ;;
    *) echo "⚠️  Unknown arg: $arg" >&2 ;;
  esac
done

echo "── check-training: py_compile of ${#PY_SCRIPTS[@]} pipeline scripts ──"
for f in "${PY_SCRIPTS[@]}"; do
  if [ -f "$f" ]; then
    python3 -m py_compile "$f"
    echo "  ✓ $(basename "$f")"
  else
    echo "  ✗ MISSING: $f"
    exit 1
  fi
done
echo "  ✅ py_compile OK"

echo "── check-training: notebook embedded-file sync (stale-trainer guard) ──"
if ! python3 scripts/sync-notebook-embedded-files.py --check; then
  echo "  ❌ stale embedded file(s) in cloud notebooks — fix with:"
  echo "     python3 scripts/sync-notebook-embedded-files.py"
  exit 1
fi
echo "  ✅ notebook embedded files in sync"

echo "── check-training: cloud-notebook cell validation (Colab + Kaggle) ──"
if ! python3 scripts/validate-cloud-notebooks.py --quiet; then
  echo "  ❌ cloud-notebook validation FAILED (broken/stale cell — see above)"
  exit 1
fi
echo "  ✅ cloud-notebook validation OK"

echo "── check-training: cloud-notebook self-test (regression guard) ──"
if ! python3 scripts/validate-cloud-notebooks.py --self-test --quiet; then
  echo "  ❌ cloud-notebook self-test FAILED — the checker no longer catches the bug it guards"
  exit 1
fi
echo "  ✅ cloud-notebook self-test OK"

if [ "$SKIP_TSC" = "1" ]; then
  echo "── check-training: --skip-tsc-test set, skipping tsc tests ──"
  exit 0
fi

# run_tsc_gate <label> <args...> — run a tsc_check-based gate, print its
# output, distinguish the tsc-not-available self-skip from a genuine PASS,
# and fail loudly (exit 1) on any failure. Output goes to a temp file so the
# test's real exit code is preserved: under `set -e` a plain OUT="$(...)"
# assignment would abort the script at the assignment itself when the test
# fails, before we could inspect and report the exit code.
run_tsc_gate() {
  local label="$1"; shift
  local tmp code
  tmp="$(mktemp)"
  python3 tests/test-tsc-concurrency.py "$@" >"$tmp" 2>&1 && code=0 || code=$?
  cat "$tmp"
  if [ "$code" = "0" ]; then
    if grep -q 'skipped' "$tmp"; then
      echo "  ⚠️  tsc not available — ${label} skipped (py_compile gate passed)"
    else
      echo "  ✅ ${label} OK"
    fi
  else
    echo "  ❌ ${label} FAILED"
    rm -f "$tmp"
    return 1
  fi
  rm -f "$tmp"
  return 0
}

echo "── check-training: tsc_check concurrency test ──"
if [ "$QUICK" = "1" ]; then
  run_tsc_gate "concurrency test" --workers 2 --threads 2 --calls 3
else
  run_tsc_gate "concurrency test" --workers 2 --threads 3 --calls 8
fi

echo "── check-training: probe self-check (--fail-on-probe-clean) ──"
if [ "$QUICK" = "1" ]; then
  run_tsc_gate "probe self-check" --fail-on-probe-clean --workers 2 --threads 2 --calls 3 --probe-rounds 3
else
  run_tsc_gate "probe self-check" --fail-on-probe-clean
fi

echo "── check-training: kaggle GPU-adaptive run-cell test ──"
if ! python3 tests/test-kaggle-adaptive-run-cell.py; then
  echo "  ❌ kaggle GPU-adaptive run-cell test FAILED"
  exit 1
fi
echo "  ✅ kaggle GPU-adaptive run-cell test OK"

echo "✅ check-training: all checks passed"
