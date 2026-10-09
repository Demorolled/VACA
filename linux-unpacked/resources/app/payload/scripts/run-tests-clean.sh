#!/usr/bin/env bash
# run-tests-clean.sh — run the backend + frontend test suites, then restore the
# files the backend suite mutates so a build leaves the worktree as it found it.
#
# Why: the backend suite writes into the knowledge store (pattern capture /
# auto-learn state), so wiring `npm run test` into `npm run build` would leave
# `backend/knowledge/*` dirty after every build. This wrapper snapshots those
# files first and copies the exact snapshot back on exit — no git assumptions,
# so any pre-existing local edits are preserved rather than clobbered.
#
# Usage (wired into the root package.json "build"):
#   bash scripts/run-tests-clean.sh
#   KNOW_FILES="backend/knowledge/patterns.json" bash scripts/run-tests-clean.sh
#
# Exits non-zero if either suite fails (the restore still runs via the trap).

set -euo pipefail
cd "$(dirname "$0")/.."

KNOW_FILES="${KNOW_FILES:-backend/knowledge/patterns.json backend/knowledge/auto-learn/auto-learn-state.json backend/knowledge/sheet-meta.json}"

BK="$(mktemp -d)"
restore() {
  local f
  for f in $KNOW_FILES; do
    if [ -f "$BK/$f" ]; then
      mkdir -p "$(dirname "$f")"
      cp -f "$BK/$f" "$f"
    fi
  done
  rm -rf "$BK"
}
trap restore EXIT

# Snapshot the CURRENT contents (whatever state the worktree is in).
for f in $KNOW_FILES; do
  if [ -f "$f" ]; then
    mkdir -p "$BK/$(dirname "$f")"
    cp -f "$f" "$BK/$f"
  fi
done

npm run test --workspace=backend
npm run test --workspace=frontend
