#!/usr/bin/env bash
# cap.sh — keep command output small enough to survive in a chat transcript.
#
# The bug this guards: one session's transcript reached 21 MB because agents
# printed whole files and raw JSON dumps. Everything printed is stored and
# re-rendered forever, which froze the client. Cap output by default.
#
# Usage:
#   some-command | scripts/cap.sh            # 40 head lines, 10 tail lines
#   some-command | scripts/cap.sh 20 5       # tighter window
#   CAP_MAX_BYTES=2000 ls -la | scripts/cap.sh
#   scripts/cap.sh --  cat huge.log          # run a command through the cap
#
# Always preserves the START of the output and the END (where errors usually
# are), and prints a marker in the middle saying how much was dropped.
set -uo pipefail

HEAD_LINES=${1:-40}
TAIL_LINES=${2:-10}
MAX_BYTES=${CAP_MAX_BYTES:-6000}
MAX_LINE_CHARS=${CAP_MAX_LINE_CHARS:-400}

# Allow `cap.sh -- cmd args...` as a wrapper as well as a pipe filter.
if [ "${1:-}" = "--" ]; then
  shift
  HEAD_LINES=${CAP_HEAD_LINES:-40}
  TAIL_LINES=${CAP_TAIL_LINES:-10}
  "$@" 2>&1 | "$0" "$HEAD_LINES" "$TAIL_LINES"
  exit $?
fi

case "$HEAD_LINES" in ''|*[!0-9]*) HEAD_LINES=40 ;; esac
case "$TAIL_LINES" in ''|*[!0-9]*) TAIL_LINES=10 ;; esac

tmp=$(mktemp) || exit 1
trap 'rm -f "$tmp"' EXIT
cat > "$tmp"

total_bytes=$(wc -c < "$tmp" | tr -d ' ')
total_lines=$(wc -l < "$tmp" | tr -d ' ')

# Single enormous line (a raw JSON blob): cut it at the byte ceiling.
if [ "$total_lines" -le 1 ] && [ "$total_bytes" -gt "$MAX_BYTES" ]; then
  head -c "$MAX_BYTES" "$tmp"
  echo
  echo "… [cap.sh] truncated at ${MAX_BYTES} bytes of ${total_bytes} total …"
  exit 0
fi

# Long lines get clipped so one 200 KB line can't defeat the window.
clip() { awk -v n="$MAX_LINE_CHARS" \
  '{ if (length($0) > n) print substr($0,1,n) " …[line clipped]"; else print }'; }

# Few enough lines to show them all: clip long lines and we're done. This is
# correct even when the byte count is over the ceiling, because clipping caps
# each line at MAX_LINE_CHARS.
if [ "$total_lines" -le $((HEAD_LINES + TAIL_LINES)) ]; then
  clip < "$tmp"
  exit 0
fi

head -n "$HEAD_LINES" "$tmp" | clip
omitted=$((total_lines - HEAD_LINES - TAIL_LINES))
echo "… [cap.sh] omitted ~${omitted} of ${total_lines} lines (${total_bytes} bytes) — save to a file if you need it all …"
tail -n "$TAIL_LINES" "$tmp" | clip
