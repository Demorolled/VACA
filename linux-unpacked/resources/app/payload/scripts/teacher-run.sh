#!/usr/bin/env bash
# teacher-run.sh — launch a teacher build in its OWN tmux session so it
# survives the terminal tool's shell cleanup (the seq-3 chess build was killed
# mid-generation by the tool killing the setsid background job; the backend had
# already produced real 14B modules but the HTTP client died before the build
# completed).
#
# Usage:
#   bash scripts/teacher-run.sh "a chess game" --purpose "3D board..." --os linux --scale medium
#
# The build runs inside tmux session "teacher-build"; its stdout goes to
# /tmp/teacher-build.log. Watch with: tail -f /tmp/teacher-build.log

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="teacher-build"
LOG="/tmp/teacher-build.log"

# Kill any previous teacher-build session (safe: only our own named session).
tmux kill-session -t "$SESSION" 2>/dev/null || true
rm -f "$LOG"

# Build the command line preserving each argument's quoting. tmux new-session
# takes ONE shell string, so re-quote every arg with printf %q.
CMD="cd '$ROOT' && python3 -u scripts/teacher-build.py"
for arg in "$@"; do
  CMD+=" $(printf '%q' "$arg")"
done
CMD+=" > '$LOG' 2>&1"

tmux new-session -d -s "$SESSION" "$CMD"

echo "teacher build launched in tmux session '$SESSION'"
echo "goal: ${1:?usage: teacher-run.sh \"GOAL\" [--purpose ...] [--os ...] [--scale ...]}"
echo "log:  $LOG  (tail -f $LOG)"
echo "session check: tmux ls | grep teacher-build"
