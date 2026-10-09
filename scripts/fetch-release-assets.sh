#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# fetch-release-assets.sh — download the prebuilt runtime from a GitHub Release
# =============================================================================
# The clone you are holding has the app's code but not the Electron runtime and
# not node_modules (see .gitignore for why). Those live on the Releases page.
# This pulls them back down:
#
#   default            fetch Veronica-<v>-linux-x64.tar.gz and extract it over
#                      the checkout, so linux-unpacked/veronica runs
#   --asset NAME       fetch just that asset (NAME may be a glob, e.g. '*.deb')
#   --all              fetch every asset on the release
#   --list             show what the release has, download nothing
#
# Assets are checked against the release's SHA256SUMS when it publishes one.
# Anything that fails the check is deleted rather than left looking usable.
#
# Usage
#   ./scripts/fetch-release-assets.sh
#   ./scripts/fetch-release-assets.sh --list
#   ./scripts/fetch-release-assets.sh --tag v1.0.0
#   ./scripts/fetch-release-assets.sh --asset '*.deb' --out ~/Downloads
#   ./scripts/fetch-release-assets.sh --all --out dist
#
# Options
#   --tag TAG      release tag (default: the latest published release)
#   --asset NAME   asset name or glob; repeatable (default: the linux-x64 tarball)
#   --all          every asset on the release
#   --out DIR      where downloads land (default: dist)
#   --list         list assets and exit
#   --no-extract   leave the tarball packed instead of restoring linux-unpacked/
#   --no-verify    skip SHA256SUMS verification
#   -h | --help
#
# Environment
#   VACA_REPO       owner/repo override (default: this clone's origin remote)
#   GITHUB_TOKEN    optional; raises the 60-requests/hour unauthenticated API cap
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
. "$ROOT/scripts/repo-slug.sh"

TAG=""
OUT="$ROOT/dist"
WANT=()
ALL=0
LIST_ONLY=0
EXTRACT=1
VERIFY=1

while [ $# -gt 0 ]; do
  case "$1" in
    --tag)        TAG="${2:?--tag needs a value}"; shift ;;
    --asset)      WANT+=("${2:?--asset needs a value}"); shift ;;
    --all)        ALL=1 ;;
    --out)        OUT="${2:?--out needs a directory}"; shift ;;
    --list)       LIST_ONLY=1 ;;
    --no-extract) EXTRACT=0 ;;
    --no-verify)  VERIFY=0 ;;
    -h|--help)    awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"; exit 0 ;;
    *) printf '\n✗ unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n── %s\n' "$*"; }
die()  { printf '\n✗ %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# GNU coreutils on Linux, shasum on macOS. The assets are Linux x64, but this
# also runs on the maintainer's laptop, where sha256sum often does not exist.
sha_check() {
  if have sha256sum; then ( cd "$OUT" && sha256sum -c "$1" )
  else ( cd "$OUT" && shasum -a 256 -c "$1" )
  fi
}

SLUG="$(repo_slug)"
if repo_slug_is_placeholder; then
  cat >&2 <<EOF

✗ No GitHub repo to fetch from.

  This clone has no origin remote, so there is nothing to resolve a release URL
  from, and the fallback slug ($SLUG) is a placeholder.

  Point it at the real repo, once:
      git remote add origin https://github.com/<owner>/<repo>.git
  or per run:
      VACA_REPO=<owner>/<repo> $0

EOF
  exit 1
fi

have curl || die "curl not found"

# ── release metadata ─────────────────────────────────────────────────────────
if [ -n "$TAG" ]; then
  API="https://api.github.com/repos/$SLUG/releases/tags/$TAG"
else
  API="https://api.github.com/repos/$SLUG/releases/latest"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step "release metadata"
say "  repo: $SLUG${TAG:+   tag: $TAG}"

auth=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
  auth=(-H "Authorization: Bearer $GITHUB_TOKEN")
fi

HTTP="$(curl -sSL -o "$TMP/release.json" -w '%{http_code}' \
          -H 'Accept: application/vnd.github+json' "${auth[@]}" "$API" || true)"
if [ "$HTTP" != "200" ]; then
  msg=""
  if have jq; then
    msg="$(jq -r '.message? // empty' "$TMP/release.json" 2>/dev/null || true)"
  elif have python3; then
    msg="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("message",""))' "$TMP/release.json" 2>/dev/null || true)"
  fi
  say "  ✗ GitHub API returned HTTP $HTTP${msg:+ — $msg}"
  if [ "$HTTP" = "404" ]; then
    say "    no published release there yet, or the repo is private (export GITHUB_TOKEN to read it)"
  fi
  exit 1
fi

# jq if we have it, else python3. Both emit "name<TAB>url".
json_assets() {
  if have jq; then
    jq -r '.assets[] | "\(.name)\t\(.browser_download_url)"' "$TMP/release.json"
  elif have python3; then
    python3 - "$TMP/release.json" <<'PY'
import json, sys
for a in json.load(open(sys.argv[1])).get("assets", []):
    print(f'{a["name"]}\t{a["browser_download_url"]}')
PY
  else
    die "need jq or python3 to read the GitHub API response"
  fi
}

json_tag() {
  if have jq; then
    jq -r '.tag_name // "unknown"' "$TMP/release.json"
  else
    python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("tag_name","unknown"))' "$TMP/release.json"
  fi
}

json_body() {
  if have jq; then
    jq -r '.body // ""' "$TMP/release.json"
  else
    python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("body","") or "")' "$TMP/release.json"
  fi
}

TAG_NAME="$(json_tag)"
mapfile -t ASSETS < <(json_assets)
[ "${#ASSETS[@]}" -gt 0 ] || die "release $TAG_NAME has no assets attached"

say "  ✓ release $TAG_NAME — ${#ASSETS[@]} asset(s)"

step "assets on $TAG_NAME"
for row in "${ASSETS[@]}"; do
  name="${row%%$'\t'*}"
  url="${row#*$'\t'}"
  bytes="$(curl -sSLI "${auth[@]}" "$url" 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /^content-length:/{v=$2} END{gsub(/\r/,"",v); print v}' || true)"
  if [ -n "$bytes" ]; then
    say "  $(printf '%-48s' "$name") $(( bytes / 1000000 )) MB"
  else
    say "  $name"
  fi
done

if [ "$LIST_ONLY" = 1 ]; then
  say ""
  notes="$(json_body | head -20)"
  if [ -n "$notes" ]; then
    step "release notes"
    printf '%s\n' "$notes" | sed 's/^/  /'
  fi
  exit 0
fi

# ── selection ────────────────────────────────────────────────────────────────
# Matches an asset name against a glob, or an exact name when it has no glob.
matches_any() {
  local name="$1"; shift
  local pat
  for pat in "$@"; do
    case "$name" in
      $pat) return 0 ;;
    esac
  done
  return 1
}

SELECTED=()
if [ "$ALL" = 1 ]; then
  for row in "${ASSETS[@]}"; do SELECTED+=("${row%%$'\t'*}"); done
else
  PATTERNS=("${WANT[@]+"${WANT[@]}"}")
  if [ "${#PATTERNS[@]}" -eq 0 ]; then
    PATTERNS=("*linux-x64.tar.gz")
  fi
  for row in "${ASSETS[@]}"; do
    name="${row%%$'\t'*}"
    if matches_any "$name" "${PATTERNS[@]}"; then SELECTED+=("$name"); fi
  done
  if [ "${#SELECTED[@]}" -eq 0 ]; then
    say ""
    die "nothing on $TAG_NAME matches: ${PATTERNS[*]}
   available: $(printf '%s ' "${ASSETS[@]%%$'\t'*}")"
  fi
fi

# ── download ─────────────────────────────────────────────────────────────────
mkdir -p "$OUT"
step "download → ${OUT#$ROOT/}"

url_of() {
  local want="$1" row
  for row in "${ASSETS[@]}"; do
    if [ "${row%%$'\t'*}" = "$want" ]; then printf '%s' "${row#*$'\t'}"; return 0; fi
  done
  return 1
}

GOT_SUMS=0
if [ "$VERIFY" = 1 ]; then
  if sums_url="$(url_of SHA256SUMS)"; then
    curl -fsSL "${auth[@]}" -o "$OUT/SHA256SUMS" "$sums_url" \
      && { GOT_SUMS=1; say "  ✓ SHA256SUMS"; }
  else
    say "  ⚠ release publishes no SHA256SUMS — cannot verify what we download"
  fi
fi

for name in "${SELECTED[@]}"; do
  url="$(url_of "$name")" || die "no URL for $name"
  if [ -s "$OUT/$name" ]; then
    say "  ✓ $name (already downloaded, reusing)"
    continue
  fi
  say "  ↓ $name"
  curl -fL --retry 3 --retry-delay 3 -C - -o "$OUT/$name" "$url" \
    || die "download failed: $name"
done

if [ "$GOT_SUMS" = 1 ]; then
  step "verify checksums"
  # Verify only what we just fetched; a partial download set must not fail on
  # assets that were deliberately not requested.
  # (\\./)? because other tools write "<hash>  ./file" after a cd'd glob. Ours
  # does not, but a maintainer regenerating the sums by hand should not be able
  # to silently defeat verification.
  ( cd "$OUT" && grep -E "  (\\./)?($(printf '%s|' "${SELECTED[@]}" | sed 's/|$//'))\$" SHA256SUMS > .want.sums || true )
  if [ -s "$OUT/.want.sums" ]; then
    if sha_check .want.sums >/dev/null 2>&1; then
      say "  ✓ all checksums match"
    else
      rm -f "$OUT/.want.sums"
      for name in "${SELECTED[@]}"; do rm -f "$OUT/$name"; done
      die "checksum mismatch — deleted the bad downloads rather than leave them looking usable"
    fi
    rm -f "$OUT/.want.sums"
  else
    say "  ⚠ nothing in SHA256SUMS covers: ${SELECTED[*]}"
  fi
fi

# ── restore the runtime ──────────────────────────────────────────────────────
TARBALL=""
for name in "${SELECTED[@]}"; do
  case "$name" in *.tar.gz) TARBALL="$name"; break ;; esac
done

if [ -n "$TARBALL" ] && [ "$EXTRACT" = 1 ]; then
  step "extract $TARBALL over the checkout"
  # The archive's top-level entry is linux-unpacked/, so this lands on top of the
  # committed tree. Files that are byte-identical (our code) are simply rewritten.
  tar -xzf "$OUT/$TARBALL" -C "$ROOT"
  if [ -x "$ROOT/linux-unpacked/veronica" ]; then
    say "  ✓ linux-unpacked/veronica is in place"
    say ""
    say "  run it:  ./linux-unpacked/veronica"
    say "  model:   ./scripts/install-model.sh   (if you have not already)"
  else
    die "extracted $TARBALL but linux-unpacked/veronica is still missing"
  fi
fi

say ""
say "✓ done — $OUT"
