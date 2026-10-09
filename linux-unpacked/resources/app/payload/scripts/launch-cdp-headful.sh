#!/usr/bin/env bash
# Headful CDP Chrome on the snapshot profile (login carried via injected key).
set -u
LOG=/tmp/cdp-chrome.log
pkill -f 'google-chrome-cdp' 2>/dev/null
sleep 2
cd /tmp
setsid /opt/google/chrome/chrome \
  --remote-debugging-port=9222 \
  --remote-allow-origins='*' \
  --user-data-dir=/home/final-flash1/.config/google-chrome-cdp \
  --no-first-run --no-default-browser-check \
  --window-size=1400,1000 --restore-last-session \
  "https://colab.research.google.com/" > "$LOG" 2>&1 < /dev/null &
PID=$!
echo "$PID" > /tmp/cdp-chrome.pid
disown 2>/dev/null || true
echo "chrome pid: $PID"
sleep 10
echo "=== CDP ==="
curl -s --max-time 3 http://127.0.0.1:9222/json/version | head -c 200
echo
ps -p "$PID" -o pid,etime --no-headers 2>/dev/null || echo "DEAD"
