#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# terminal-speak-start.sh — start the terminal auto-speak daemon.
#
# The daemon is normally supervised by the systemd user service
# (scripts/terminal-speak.service, installed at
# ~/.config/systemd/user/terminal-speak.service) which auto-restarts it on
# crash and starts it at login.
#
# This script is the manual entry point:
#   - if the systemd user service is installed, start it via systemctl
#     (so there is only ever ONE instance and systemd keeps supervision);
#   - otherwise fall back to launching the daemon detached with setsid
#     (no tmux dependency — tmux is not installed on this box).
#
# Usage:
#   bash scripts/terminal-speak-start.sh     start (idempotent)
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAEMON="$ROOT/scripts/terminal-autospeak.py"
LOG="$ROOT/scripts/terminal-speak.log"

if command -v systemctl >/dev/null 2>&1 \
        && systemctl --user cat terminal-speak.service >/dev/null 2>&1; then
    systemctl --user start terminal-speak.service
    echo "[terminal-speak] systemd user service started (voice en-US-JennyNeural)"
    exit 0
fi

# Fallback: no systemd unit — run detached. The bracket in "[t]erminal-autospeak"
# keeps this pattern from matching the pgrep process itself; this script's own
# command line names only this script, so only a real daemon matches.
if pgrep -f "[t]erminal-autospeak\.py" >/dev/null 2>&1; then
    echo "[terminal-speak] already running — nothing to do"
    exit 0
fi

if [ ! -f "$DAEMON" ]; then
    echo "[terminal-speak] daemon not found: $DAEMON" >&2
    exit 1
fi

setsid nohup python3 "$DAEMON" >> "$LOG" 2>&1 < /dev/null &
echo "[terminal-speak] started detached (pid $!) — voice en-US-JennyNeural, log $LOG"
