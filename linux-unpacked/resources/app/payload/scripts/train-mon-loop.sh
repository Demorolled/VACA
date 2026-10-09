#!/usr/bin/env bash
# train-mon-loop.sh — persistent R23 monitor. Run it inside tmux or a desktop
# terminal so it survives SSH/VNC disconnects. Refreshes every 5s.
LOG="${1:-training/cloud/round23-train.log}"
cd "$(dirname "$0")/.." || exit 1
echo "R23 monitor — Ctrl+C to stop. Log: $LOG"
sleep 2
while true; do
  clear
  bash scripts/train-mon.sh "$LOG"
  sleep 5
done
