#!/usr/bin/env bash
# Headful CDP Chrome for the Lightning AI studio (port 9226) on the CDP
# snapshot profile — the browser we can automate for uploads + training.
set -u
LOG=/tmp/cdp-lightning.log
PORT=9226
URL="${LIGHTNING_URL:-https://lightning.ai/bigstuff2gs-org/financial-llm-training-project/studios/training-devbox/code}"

pkill -f "remote-debugging-port=$PORT" 2>/dev/null
sleep 2

# Clear stale single-instance locks from the snapshot profile
PROF=/home/final-flash1/.config/google-chrome-cdp
rm -f "$PROF/SingletonLock" "$PROF/SingletonCookie" "$PROF/SingletonSocket" 2>/dev/null

cd /tmp
setsid /opt/google/chrome/chrome \
  --remote-debugging-port=$PORT \
  --remote-allow-origins='*' \
  --user-data-dir=/home/final-flash1/.config/google-chrome-cdp \
  --no-first-run --no-default-browser-check \
  --window-size=1440,1000 \
  "$URL" > "$LOG" 2>&1 < /dev/null &
PID=$!
echo "$PID" > /tmp/cdp-lightning.pid
disown 2>/dev/null || true
echo "chrome pid: $PID"
sleep 10
echo "=== CDP ==="
curl -s --max-time 3 "http://127.0.0.1:$PORT/json/version" | head -c 200
echo
echo "=== tabs ==="
curl -s --max-time 3 "http://127.0.0.1:$PORT/json/list" | python3 -c 'import json,sys; [print(t.get("type"),"|",t.get("url","")[:90]) for t in json.load(sys.stdin)]' 2>/dev/null | head -8
ps -p "$PID" -o pid,etime --no-headers 2>/dev/null || echo "DEAD"
