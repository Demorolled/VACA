#!/usr/bin/env bash
#
# install-toolchains.sh — install every compiler/gate toolchain VACA uses.
#
# VACA's non-TS compile gate (backend/src/sandbox/nonTsCompileGate.ts) shells out
# to the real toolchain for each language it supports. An unavailable toolchain
# is reported as a FAILED gate ("unverified is never clean"), so a box without
# these tools can never verify a Rust/C++/Go/... build. This script installs the
# whole set so every gate can actually run.
#
# Core desktop/server set: C, C++, Rust, Go, Java, C#, Python, PHP, Ruby, Node.
# (Swift/Kotlin are gateable but mobile/mac-centric — install them separately.)
#
# Usage:
#   scripts/install-toolchains.sh            # install everything missing
#   scripts/install-toolchains.sh --check    # report what's present, install nothing
#
# Windows: use scripts/install-toolchains.ps1 instead.
set -euo pipefail

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
miss() { printf '\033[1;33m  •\033[0m %s\n' "$*"; }

# ── Report ────────────────────────────────────────────────────────────────
report() {
  say "Toolchain status"
  local bin
  for bin in gcc g++ rustc go javac dotnet python3 php ruby node kotlinc swiftc; do
    if have "$bin"; then ok "$bin $("$bin" --version 2>&1 | head -1)"; else miss "$bin MISSING"; fi
  done
}
report
[ "$CHECK_ONLY" = "1" ] && exit 0

# ── Package manager ───────────────────────────────────────────────────────
if have apt-get; then PM=apt
elif have dnf; then PM=dnf
elif have pacman; then PM=pacman
elif have brew; then PM=brew
elif have zypper; then PM=zypper
else echo "No supported package manager (apt/dnf/pacman/zypper/brew) found." >&2; exit 1
fi
say "Using package manager: $PM"

SUDO=""
if [ "$(id -u)" != "0" ] && have sudo; then SUDO="sudo"; fi

pm_install() { # pm_install <apt-name>... (dnf/pacman/brew names passed as-is where shared)
  case "$PM" in
    apt)    $SUDO apt-get install -y "$@" ;;
    dnf)    $SUDO dnf install -y "$@" ;;
    zypper) $SUDO zypper --non-interactive install "$@" ;;
    pacman) $SUDO pacman -Sy --noconfirm "$@" ;;
    brew)   brew install "$@" ;;
  esac
}

# ── C / C++ (gcc/g++) ─────────────────────────────────────────────────────
if ! have gcc || ! have g++; then
  say "Installing C/C++ toolchain"
  case "$PM" in
    apt)  pm_install build-essential ;;
    dnf)  pm_install gcc gcc-c++ make ;;
    zypper|pacman) pm_install gcc g++ make ;;
    brew) pm_install gcc ;;
  esac
fi

# ── Python ────────────────────────────────────────────────────────────────
have python3 || { say "Installing Python"; case "$PM" in
  apt) pm_install python3 ;; dnf) pm_install python3 ;; zypper) pm_install python3 ;;
  pacman) pm_install python ;; brew) pm_install python ;; esac; }

# ── Java (JDK 17) ─────────────────────────────────────────────────────────
have javac || { say "Installing OpenJDK 17"; case "$PM" in
  apt) pm_install openjdk-17-jdk-headless ;; dnf) pm_install java-17-openjdk-devel ;;
  zypper) pm_install java-17-openjdk-devel ;; pacman) pm_install jdk17-openjdk ;;
  brew) pm_install openjdk@17 ;; esac; }

# ── PHP ───────────────────────────────────────────────────────────────────
have php || { say "Installing PHP"; case "$PM" in
  apt) pm_install php-cli ;; dnf) pm_install php-cli ;; zypper) pm_install php ;;
  pacman) pm_install php ;; brew) pm_install php ;; esac; }

# ── Ruby ──────────────────────────────────────────────────────────────────
have ruby || { say "Installing Ruby"; case "$PM" in
  apt) pm_install ruby-full ;; dnf) pm_install ruby ;; zypper) pm_install ruby ;;
  pacman) pm_install ruby ;; brew) pm_install ruby ;; esac; }

# ── Go ────────────────────────────────────────────────────────────────────
have go || { say "Installing Go"; case "$PM" in
  apt) pm_install golang-go ;; dnf) pm_install golang ;; zypper) pm_install go ;;
  pacman) pm_install go ;; brew) pm_install go ;; esac; }

# ── .NET SDK (provides the C# compiler / dotnet) ──────────────────────────
have dotnet || { say "Installing .NET SDK 8"; case "$PM" in
  apt) pm_install dotnet-sdk-8.0 || {
         # Not in every apt repo — fall back to the official installer script.
         curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0
       } ;;
  dnf) pm_install dotnet-sdk-8.0 ;; zypper) pm_install dotnet-sdk-8.0 ;;
  pacman) pm_install dotnet-sdk ;; brew) pm_install dotnet ;; esac; }

# ── Rust (rustup — distro rustc packages are usually stale) ───────────────
have rustc || { say "Installing Rust via rustup";
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
  # shellcheck disable=SC1091
  [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"; }

# ── Kotlin (JVM — same binary on Windows/Linux/macOS) ─────────────────────
have kotlinc || { say "Installing Kotlin"; case "$PM" in
  brew) pm_install kotlin ;;
  *) if have snap; then sudo snap install kotlin --classic; else pm_install kotlin; fi ;;
  esac; }

# ── Swift (swiftly — NOT the apt `swift` package, which is OpenStack Swift) ──
if ! have swiftc; then
  say "Installing Swift via swiftly"
  ( cd "$(mktemp -d)" \
    && curl -fsSL -O "https://download.swift.org/swiftly/linux/swiftly-$(uname -m).tar.gz" \
    && tar zxf "swiftly-$(uname -m).tar.gz" \
    && ./swiftly init --quiet-shell-followup --assume-yes \
    && . "${SWIFTLY_HOME_DIR:-$HOME/.local/share/swiftly}/env.sh" \
    && swiftly install latest ) || echo "  (swiftly init failed — see swift.org/install/linux)"
fi

# ── Node.js (the pipeline itself runs on it) ──────────────────────────────
have node || { say "Installing Node.js"; case "$PM" in
  apt) pm_install nodejs npm ;; dnf) pm_install nodejs npm ;; zypper) pm_install nodejs npm ;;
  pacman) pm_install nodejs npm ;; brew) pm_install node ;; esac; }

echo
say "Done."
report
cat <<'EOF'

If a binary was just installed and is still not found, open a new shell
(or source the tool's env, e.g. `. "$HOME/.cargo/env"` for Rust).
Verify with:  cd backend && npm run toolchains:report
EOF
