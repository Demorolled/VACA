#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# make-release.sh — package VACA for distribution.
#
# Bundles EVERYTHING the app needs to run, including the gitignored-but-runtime
# deps a naive `git archive` would silently omit:
#   - models/*.gguf          (the VACA-trained model — bundled by design)
#   - data/rico/             (RICO UI-pattern dataset, loaded by GuiBuilderTool)
#   - knowledge/rnn-model.json (neural trainer / knowledge routes)
#
# NOT included (not needed at runtime):
#   - data/galaxy/           (only referenced in a comment; patterns come from
#                             data/ui-patterns/patterns.json, which IS tracked)
#   - tools/voice/.venv      (local TTS/STT tooling, user-specific)
#   - llm-training-app/data/uploads  (studio uploads, user-specific)
#   - .git history
#
# Usage:
#   bash scripts/make-release.sh              # build release/vaca/ + tarball
#   bash scripts/make-release.sh --no-tar     # only stage the directory
#   bash scripts/make-release.sh --with-npm   # also run `npm ci` in the release
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT/release/vaca"
TAR="$ROOT/release/vaca-$(date +%Y%m%d-%H%M%S).tar.gz"
DO_TAR=1
DO_NPM=0
for arg in "$@"; do
  case "$arg" in
    --no-tar) DO_TAR=0 ;;
    --with-npm) DO_NPM=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 1 ;;
  esac
done

echo "═══ VACA release packaging ═══"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# 1. All tracked source (git is the source of truth for the app code).
#    Filter to files that still exist — git ls-files lists deleted-but-unstaged
#    paths (e.g. cleaned-up exports) which would abort the copy.
echo "─ 1/5 tracked source (git ls-files)…"
(cd "$ROOT" && git ls-files -z | while IFS= read -r -d '' f; do
  [ -f "$f" ] && cp --parents "$f" "$RELEASE_DIR/"
done)

# 2. The trained model — bundled by design (trained for VACA).
echo "─ 2/5 model GGUF…"
if ls "$ROOT"/models/*.gguf >/dev/null 2>&1; then
  mkdir -p "$RELEASE_DIR/models"
  cp "$ROOT"/models/*.gguf "$RELEASE_DIR/models/"
  du -sh "$RELEASE_DIR/models/" | sed 's/^/    /'
else
  echo "    WARNING: no models/*.gguf found — release will not run offline"
fi

# 3. RICO dataset (runtime dep of GuiBuilderTool) — data JSON only, no nested .git.
echo "─ 3/5 rico dataset…"
if [ -d "$ROOT/data/rico/rico_semantics/data" ]; then
  mkdir -p "$RELEASE_DIR/data/rico"
  cp -r "$ROOT/data/rico/rico_semantics" "$RELEASE_DIR/data/rico/"
  rm -rf "$RELEASE_DIR/data/rico/rico_semantics/.git"
  du -sh "$RELEASE_DIR/data/rico/" | sed 's/^/    /'
else
  echo "    WARNING: data/rico missing — GUI builder will degrade gracefully"
fi

# 4. Root knowledge/rnn-model.json (gitignored but read at runtime).
echo "─ 4/5 root knowledge…"
if [ -f "$ROOT/knowledge/rnn-model.json" ]; then
  mkdir -p "$RELEASE_DIR/knowledge"
  cp "$ROOT/knowledge/rnn-model.json" "$RELEASE_DIR/knowledge/"
  echo "    copied knowledge/rnn-model.json"
else
  echo "    WARNING: knowledge/rnn-model.json missing"
fi

# 5. Dependencies (optional) + summary.
if [ "$DO_NPM" = "1" ]; then
  echo "─ 5/5 npm ci…"
  (cd "$RELEASE_DIR" && npm ci --silent)
else
  echo "─ 5/5 skipping npm ci (run 'npm ci' in release/vaca/ at deploy)"
fi

echo ""
echo "═══ Staged: $RELEASE_DIR ═══"
du -sh "$RELEASE_DIR"

if [ "$DO_TAR" = "1" ]; then
  echo "═══ Tarring… ═══"
  tar -czf "$TAR" -C "$(dirname "$RELEASE_DIR")" vaca
  echo "═══ Done: $TAR ═══"
  ls -lh "$TAR" | awk '{print $5, $9}'
  echo "Deploy:  tar -xzf $(basename "$TAR") && cd vaca && npm ci && npm start"
fi
