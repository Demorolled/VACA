#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build-release-assets.sh — stage the files that go on a GitHub Release
# =============================================================================
# Three files are too big to live in git (two of them are over GitHub's 100 MB
# hard per-file limit), so they are release assets instead. This script collects
# them into dist/, hashes them, and prints the exact upload command.
#
#   dist/Veronica-<version>.AppImage                 portable, needs libfuse2
#   dist/veronica_<version>_amd64.deb                apt/dpkg install
#   dist/Veronica-<version>-linux-x64.tar.gz         self-contained runtime dir
#   dist/SHA256SUMS                                  checksums for all three
#
# The tarball is the whole linux-unpacked/ tree, node_modules included: that is
# what makes it runnable on a machine with no Node and no FUSE. It is also what
# scripts/fetch-release-assets.sh extracts back over a clone.
#
# Nothing here is committed — dist/ is gitignored.
#
# Usage
#   ./scripts/build-release-assets.sh
#   ./scripts/build-release-assets.sh --out /tmp/v1.0.0
#   ./scripts/build-release-assets.sh --skip-tarball      # AppImage + .deb only
#   ./scripts/build-release-assets.sh --recompress        # rebuild the .tar.gz
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

OUT="$ROOT/dist"
SKIP_TARBALL=0
RECOMPRESS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --out)          OUT="${2:?--out needs a directory}"; shift ;;
    --skip-tarball) SKIP_TARBALL=1 ;;
    --recompress)   RECOMPRESS=1 ;;
    -h|--help)      awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"; exit 0 ;;
    *) printf '\n✗ unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n── %s\n' "$*"; }
die()  { printf '\n✗ %s\n' "$*" >&2; exit 1; }

# sha256sum on Linux, shasum -a 256 on macOS. Both write the same "<hash>  <file>"
# format, which is what fetch-release-assets.sh verifies against.
sha_tool() {
  if command -v sha256sum >/dev/null 2>&1; then printf 'sha256sum'; return; fi
  if command -v shasum >/dev/null 2>&1; then printf 'shasum -a 256'; return; fi
  die "need sha256sum or shasum to write SHA256SUMS"
}

APP_PKG="$ROOT/linux-unpacked/resources/app/package.json"
[ -f "$APP_PKG" ] || die "not a Veronica checkout: $APP_PKG is missing"
VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$APP_PKG" | head -1)"
[ -n "$VERSION" ] || die "could not read \"version\" from $APP_PKG"

say "Veronica $VERSION — staging release assets into $OUT"
mkdir -p "$OUT"

missing=0
stage() {
  local src="$1" dst="$2"
  if [ ! -f "$src" ]; then
    say "✗ missing: ${src#$ROOT/}"
    missing=$((missing + 1))
    return 1
  fi
  step "stage $(basename "$dst")"
  cp -f "$src" "$dst"
  say "  ${src#$ROOT/} → ${dst#$ROOT/}  ($(du -h "$dst" | cut -f1))"
}

stage "$ROOT/Veronica-$VERSION.AppImage"    "$OUT/Veronica-$VERSION.AppImage"    || true
stage "$ROOT/veronica_${VERSION}_amd64.deb" "$OUT/veronica_${VERSION}_amd64.deb" || true

if [ "$SKIP_TARBALL" = 0 ]; then
  step "pack linux-unpacked/ → Veronica-$VERSION-linux-x64.tar.gz"
  [ -x "$ROOT/linux-unpacked/veronica" ] \
    || die "linux-unpacked/veronica is missing — that tree is the runnable runtime; restore it before packaging"
  if [ -f "$OUT/Veronica-$VERSION-linux-x64.tar.gz" ] && [ "$RECOMPRESS" = 0 ]; then
    say "  already present, keeping it (--recompress to rebuild)"
  else
    # -C so the archive's top-level entry is linux-unpacked/, never ./ or an
    # absolute path: extracting it at the repo root has to land back on top of
    # the checkout, which is what fetch-release-assets.sh relies on.
    tar -C "$ROOT" -czf "$OUT/Veronica-$VERSION-linux-x64.tar.gz" linux-unpacked
    say "  $(du -h "$OUT/Veronica-$VERSION-linux-x64.tar.gz" | cut -f1)"
  fi
fi

step "checksums"
# Bare filenames, no leading ./ — that is the conventional SHA256SUMS layout and
# what fetch-release-assets.sh's lookup expects. Globs that match nothing are
# passed through literally and error out; stderr is dropped, the matches still
# get hashed, and a wholly empty result is caught below.
( cd "$OUT" && $(sha_tool) *.AppImage *.deb *.tar.gz 2>/dev/null > SHA256SUMS || true )
if [ -s "$OUT/SHA256SUMS" ]; then
  sed 's/^/  /' "$OUT/SHA256SUMS"
else
  say "  ✗ nothing to hash — no assets were staged"
  missing=$((missing + 1))
fi

# GitHub's ceiling is 2 GB per asset and 100 MB per file in git. Say so now
# rather than after a failed upload.
step "size check"
oversize=0
for f in "$OUT"/*.AppImage "$OUT"/*.deb "$OUT"/*.tar.gz; do
  [ -f "$f" ] || continue
  bytes=$(stat -Lc %s "$f")
  mb=$(( bytes / 1000000 ))
  if [ "$bytes" -gt 2000000000 ]; then
    say "  ✗ $(basename "$f") is ${mb} MB — over GitHub's 2 GB per-asset limit, split it"
    oversize=$((oversize + 1))
  elif [ "$bytes" -gt 100000000 ]; then
    say "  ✓ $(basename "$f") ${mb} MB — release asset only, must never be committed to git"
  else
    say "  ✓ $(basename "$f") ${mb} MB"
  fi
done

# shellcheck source=repo-slug.sh
. "$ROOT/scripts/repo-slug.sh"
SLUG="$(repo_slug)"

step "upload"
say "  repo: $SLUG"
if [ "$SLUG" != "$VACA_REPO_DEFAULT" ]; then
  say "  ⚠ resolves to a repo other than $VACA_REPO_DEFAULT (origin remote?)"
fi
if ! command -v gh >/dev/null 2>&1; then
  say "  ⚠ the gh CLI is not installed — install it, then 'gh auth login'"
fi
say ""

say "    gh release create v$VERSION \\"
for f in "$OUT"/*.AppImage "$OUT"/*.deb "$OUT"/*.tar.gz "$OUT"/SHA256SUMS; do
  [ -f "$f" ] || continue
  say "        $OUT/$(basename "$f") \\"
done
if [ -f "$ROOT/RELEASE_NOTES.md" ]; then
  say "        --repo $SLUG --title \"Veronica $VERSION\" --notes-file RELEASE_NOTES.md"
else
  say "        --repo $SLUG --title \"Veronica $VERSION\" --generate-notes"
fi
say ""
say "  Before tagging: upload the model separately (it is never a release asset)."
say "  Use Hugging Face for the ~9 GB tuned GGUF and link it from the notes:"
say "      ./scripts/install-model.sh --tuned --gguf-url <the HF URL>"
say "  (or set TUNED_GGUF_URL in scripts/install-model.sh, once, for everyone)"

if [ "$missing" -gt 0 ] || [ "$oversize" -gt 0 ]; then
  say ""
  say "✗ finished with problems (missing=$missing oversize=$oversize)"
  exit 1
fi

say ""
say "✓ assets staged in $OUT"
