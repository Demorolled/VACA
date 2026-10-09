#!/usr/bin/env bash
# kaggle-poll-round16.sh — lightweight status poller for the R16 kernel.
# Logs every status change (plus heartbeat) to a file. Does NOT download,
# merge, or deploy — that remains a manual decision when training completes.
#
# Usage: bash scripts/kaggle-poll-round16.sh [seconds_between_polls] [max_minutes]
set -euo pipefail

KERNEL="stevenawoods/vaca-r16-anti-fence-clean-round-resume-r15"
POLL_SECONDS="${1:-300}"      # default: every 5 minutes
MAX_MINUTES="${2:-420}"       # default: up to 7 hours
LOG="/tmp/kaggle-r16-poll.log"

mkdir -p "$(dirname "$LOG")"
echo "[$(date -Is)] poller started: every ${POLL_SECONDS}s, max ${MAX_MINUTES}m" >> "$LOG"

END=$(( $(date +%s) + MAX_MINUTES * 60 ))
LAST_STATUS=""
LAST_CHANGE_AT=$(date +%s)

while [ "$(date +%s)" -lt "$END" ]; do
  STATUS=$(timeout 60 kaggle kernels status "$KERNEL" 2>&1 | head -1 | sed -E 's/.*status "//; s/".*//' || echo "POLL_ERROR")
  NOW=$(date +%s)

  if [ "$STATUS" != "$LAST_STATUS" ]; then
    echo "[$(date -Is)] STATUS CHANGE → ${STATUS} (was ${LAST_STATUS:-none}, after $(( (NOW - LAST_CHANGE_AT) / 60 ))m in current state)" >> "$LOG"
    LAST_STATUS="$STATUS"
    LAST_CHANGE_AT=$NOW
    # Also tee to stdout so a foreground invocation shows progress
    echo "[$(date -Is)] ${STATUS}"
  fi

  # Quick exit on terminal states
  case "$STATUS" in
    *COMPLETE*|*SUCCESS*|*ERROR*|*FAILED*|*CANCELED*)
      echo "[$(date -Is)] terminal state reached (${STATUS}) — exiting poller" >> "$LOG"
      exit 0
      ;;
  esac

  sleep "$POLL_SECONDS"
done

echo "[$(date -Is)] poller reached max time (${MAX_MINUTES}m) — exiting" >> "$LOG"
exit 0
