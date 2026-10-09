#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run-from-checkout.sh — run Veronica straight from a clone
# =============================================================================
# No .deb, no AppImage, no FUSE. Two ways, picked automatically:
#
#   A. linux-unpacked/veronica exists (a release tarball was extracted, or you
#      are on the machine that was packaged)  → launch it, nothing to install.
#
#   B. it does not → this is a code-only clone. Install the payload's runtime
#      deps and run the app on a locally installed Electron of the same major.
#      That is a ~250 MB npm download the first time.
#
# Either way the app then does its usual first-run staging into
# ~/.config/Veronica/runtime and starts its own backend.
#
# Usage
#   ./scripts/run-from-checkout.sh
#   ./scripts/run-from-checkout.sh --fetch          # download the release runtime first
#   ./scripts/run-from-checkout.sh --install-only   # deps + Electron, do not launch
#   ./scripts/run-from-checkout.sh --print-cmd      # show what would run
#
# Environment
#   VACA_ELECTRON_VERSION   Electron major to install (default 44, the version
#                           this build was packaged with)
#   PLAYWRIGHT_BROWSERS     1 to let the deps install download a Chromium for
#                           the render-smoke gate (~150 MB). Default: skipped.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
APP_DIR="$ROOT/linux-unpacked/resources/app"
PAYLOAD_DIR="$APP_DIR/payload"

FETCH=0
INSTALL_ONLY=0
PRINT_CMD=0
ELECTRON_MAJOR="${VACA_ELECTRON_VERSION:-44}"

while [ $# -gt 0 ]; do
  case "$1" in
    --fetch)        FETCH=1 ;;
    --install-only) INSTALL_ONLY=1 ;;
    --print-cmd)    PRINT_CMD=1 ;;
    -h|--help)      awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"; exit 0 ;;
    *) printf '\n✗ unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n── %s\n' "$*"; }
die()  { printf '\n✗ %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ── Chromium's sandbox ───────────────────────────────────────────────────────
# Electron refuses to start unless ONE of these holds:
#   a. chrome-sandbox is setuid root (owner root, mode 4755), or
#   b. the kernel allows unprivileged user namespaces for this process.
# A plain unpacked tree has (a) unset — the file ships mode 755 — and Ubuntu
# 24.04+ sets kernel.apparmor_restrict_unprivileged_userns=1, which kills (b)
# for anything without an AppArmor profile. The result is an abort that reads
# like a corrupted install:
#   "The SUID sandbox helper binary was found, but is not configured correctly"
# So detect it here and pass --no-sandbox rather than hand over a failure. This
# is the same trade the .deb/appimage paths need (see README ▸ Troubleshooting).
sandbox_args() {
  local helper="$1"
  if [ -e "$helper" ]; then
    case "$(stat -Lc '%u %a' "$helper" 2>/dev/null)" in
      "0 4755") return 0 ;;   # real setuid sandbox, use it
    esac
  fi
  if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || printf 0)" = "1" ]; then
    printf -- '--no-sandbox'
  fi
}

announce_sandbox() {
  local args="$1"
  if [ -n "$args" ]; then
    say "  ⚠ chrome-sandbox is not setuid, and this kernel restricts unprivileged"
    say "    user namespaces (Ubuntu 24.04+ default) — starting with --no-sandbox."
    say "    To get the sandbox instead, run once:"
    say "        sudo chown root:root <app dir>/chrome-sandbox && sudo chmod 4755 <app dir>/chrome-sandbox"
  fi
}

[ -f "$APP_DIR/main.js" ] || die "not a Veronica checkout: $APP_DIR/main.js is missing"
[ -f "$PAYLOAD_DIR/package.json" ] || die "payload is missing: $PAYLOAD_DIR/package.json"

if [ "$FETCH" = 1 ]; then
  "$ROOT/scripts/fetch-release-assets.sh"
fi

# ── path A: the prebuilt runtime is already here ─────────────────────────────
if [ -x "$ROOT/linux-unpacked/veronica" ] && [ -d "$PAYLOAD_DIR/node_modules" ]; then
  step "prebuilt runtime"
  say "  ✓ linux-unpacked/veronica is present — launching it directly"
  SANDBOX="$(sandbox_args "$ROOT/linux-unpacked/chrome-sandbox")"
  announce_sandbox "$SANDBOX"
  if [ "$PRINT_CMD" = 1 ]; then
    say "  would exec: $ROOT/linux-unpacked/veronica ${SANDBOX:+$SANDBOX }"
    exit 0
  fi
  if [ "$INSTALL_ONLY" = 1 ]; then exit 0; fi
  # shellcheck disable=SC2086  # SANDBOX is a deliberate word-split flag list
  exec "$ROOT/linux-unpacked/veronica" $SANDBOX
fi

# ── path B: code-only clone ──────────────────────────────────────────────────
step "no prebuilt runtime — preparing a dev run"
if [ -x "$ROOT/linux-unpacked/veronica" ]; then
  say "  linux-unpacked/veronica exists but payload/node_modules does not;"
  say "  the payload still has to be installed either way."
else
  say "  linux-unpacked/veronica is absent."
  say "  (fastest alternative: ./scripts/run-from-checkout.sh --fetch)"
fi

have node || die "node not found — install Node, or use the .deb / AppImage from Releases"
have npm  || die "npm not found — install Node, or use the .deb / AppImage from Releases"
say "  node $(node -v)  npm $(npm -v)"

# The deps are pure JS apart from esbuild's prebuilt binary, so a modern Node is
# fine. --omit=dev because there are no dev dependencies in this tree; it keeps
# a test toolchain out of the install.
#
# Playwright's postinstall pulls a whole browser. Nothing in the app needs it to
# boot — the render-smoke gate degrades to its TS engine without it — so it is
# skipped unless PLAYWRIGHT_BROWSERS=1. Otherwise a "just run it" command would
# quietly add 150 MB to the download.
if [ ! -d "$PAYLOAD_DIR/node_modules" ]; then
  step "install payload dependencies"
  if [ -f "$PAYLOAD_DIR/package-lock.json" ]; then
    # `npm ci` installs exactly the committed lock and refuses if package.json
    # and the lock disagree, which is the whole point of committing the lock.
    say "  npm --prefix ${PAYLOAD_DIR#$ROOT/} ci --omit=dev"
    if [ "${PLAYWRIGHT_BROWSERS:-0}" = "1" ]; then
      npm --prefix "$PAYLOAD_DIR" ci --omit=dev
    else
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm --prefix "$PAYLOAD_DIR" ci --omit=dev
    fi
  else
    say "  npm --prefix ${PAYLOAD_DIR#$ROOT/} install --omit=dev  (no lockfile committed)"
    if [ "${PLAYWRIGHT_BROWSERS:-0}" = "1" ]; then
      npm --prefix "$PAYLOAD_DIR" install --omit=dev
    else
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm --prefix "$PAYLOAD_DIR" install --omit=dev
    fi
  fi
else
  say "  ✓ payload/node_modules already installed"
fi

if [ ! -x "$APP_DIR/node_modules/.bin/electron" ]; then
  step "install Electron $ELECTRON_MAJOR"
  say "  npm --prefix ${APP_DIR#$ROOT/} install --no-save electron@$ELECTRON_MAJOR"
  # --no-save / --no-package-lock: app/package.json is the packaged app's
  # manifest. Rewriting it (or dropping a lock beside it) would change what a
  # future electron-builder run produces, and would show up as a dirty tree.
  npm --prefix "$APP_DIR" install --no-save --no-package-lock "electron@$ELECTRON_MAJOR"
else
  say "  ✓ Electron already installed in the app dir"
fi

step "launch"
SANDBOX="$(sandbox_args "$APP_DIR/node_modules/electron/dist/chrome-sandbox")"
announce_sandbox "$SANDBOX"
if [ "$PRINT_CMD" = 1 ]; then
  say "  would exec: $APP_DIR/node_modules/.bin/electron ${SANDBOX:+$SANDBOX }$APP_DIR"
  exit 0
fi
if [ "$INSTALL_ONLY" = 1 ]; then
  say "  --install-only given, not launching"
  exit 0
fi

say "  electron ${SANDBOX:+$SANDBOX }$APP_DIR"
say ""
say "  note: this runs the app from the clone. main.js still stages a working"
say "  copy into ~/.config/Veronica/runtime, so nothing is written back here."
# shellcheck disable=SC2086  # SANDBOX is a deliberate word-split flag list
exec "$APP_DIR/node_modules/.bin/electron" $SANDBOX "$APP_DIR"
