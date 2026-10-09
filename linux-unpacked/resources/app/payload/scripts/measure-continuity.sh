#!/usr/bin/env bash
# Measure the emotion continuity pass rate over 3 live runs of
# verify-blueprint-emotion.py (each ~2.5 min: blueprint build + 2 chats).
cd "$(dirname "$0")/.."
for i in 1 2 3; do
  echo "=== RUN $i ==="
  timeout 300 python3 -u scripts/verify-blueprint-emotion.py 2>&1 \
    | grep -E 'turn1 warm|PASS — continuity|soul freshness|PASS — emotion' | head -4
  sleep 2
done
echo "=== DONE ==="
