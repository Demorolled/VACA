#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# agent-gemma-serve.sh — stop / status / start the gemma-4-12B dspark server
# =============================================================================
# The agent computer serves gemma-4-12B across its 3× RTX 3060 on port 8000.
# During local training we PAUSE this serve (to free all 36 GB VRAM), then restart
# it afterward. This script makes pause + restart safe and exact.
#
# Usage (as user llmlab on 192.168.1.234):
#   bash scripts/agent-gemma-serve.sh status    # is it up? which pid?
#   bash scripts/agent-gemma-serve.sh stop      # graceful SIGTERM, wait for exit
#   bash scripts/agent-gemma-serve.sh start     # detached relaunch (exact original cmd)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="/home/llmlab/Desktop/visual-ai-architect"
CMD='python3 scripts/dspark_server.py --target /home/llmlab/Desktop/visual-ai-architect/models/gemma4-q4/gemma-4-12B-it-abliterated-uncensored.Q4_K_M.gguf --draft qwen2.5-coder:0.5b --port 8000 --n-ctx 16384 --n-batch 512 --n-gpu-layers -1 --draft-mode none --split-mode layer --tensor-split 0.34,0.33,0.33 --flash-attn'
LOGFILE="$ROOT/data/dspark-gemma.log"
PIDFILE="/tmp/dspark-gemma.pid"

mode="${1:-status}"
mkdir -p "$(dirname "$LOGFILE")"

pid_of() { pgrep -f "dspark_server.py" | head -1; }

case "$mode" in
  status)
    pid=$(pid_of)
    if [ -n "$pid" ]; then
      echo "UP pid=$pid port_check=$(curl -s -m 3 http://127.0.0.1:8000/health 2>/dev/null | head -c 60 || echo '(no resp)')"
    else
      echo "DOWN (no dspark_server process)"
    fi
    ;;
  stop)
    pid=$(pid_of)
    if [ -z "$pid" ]; then echo "already down"; exit 0; fi
    echo "stopping dspark pid=$pid..."
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do
      if [ -z "$(pid_of)" ]; then echo "stopped"; exit 0; fi
      sleep 1
    done
    kill -9 "$pid" 2>/dev/null
    echo "stopped (killed -9)"
    ;;
  start)
    pid=$(pid_of)
    if [ -n "$pid" ]; then echo "already up pid=$pid"; exit 0; fi
    cd "$ROOT"
    setsid bash -c "cd '$ROOT' && $CMD > '$LOGFILE' 2>&1 < /dev/null & disown" 
    echo "starting dspark detached → $LOGFILE"
    sleep 2
    echo "pid=$(pid_of)"
    ;;
  *) echo "usage: $0 {status|stop|start}"; exit 2 ;;
esac