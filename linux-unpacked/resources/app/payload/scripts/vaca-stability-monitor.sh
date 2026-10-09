#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# vaca-stability-monitor.sh — confirm the VACA app stops crash-looping.
#
# Samples every INTERVAL seconds for DURATION and appends one line per sample
# to the log: systemd restart counters for dspark.service + vaca-monitor.service,
# backend/frontend/dspark health, tmux state, and the PIDs of the key
# processes. A PID change between samples means the process was restarted.
#
# Usage:
#   bash scripts/vaca-stability-monitor.sh            # default: 4h, every 3min
#   bash scripts/vaca-stability-monitor.sh 2          # 2 hours
#   bash scripts/vaca-stability-monitor.sh 2 60       # 2h, every 60s
#   bash scripts/vaca-stability-monitor.sh --stop     # stop a running instance
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/scripts/monitor-stability.log"
PID_FILE="$ROOT/scripts/monitor-stability.pid"
DURATION_H="${1:-4}"
INTERVAL="${2:-180}"

say() { printf '\033[1;34m[stability-monitor]\033[0m %s\n' "$*"; }

if [ "${1:-}" = "--stop" ]; then
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")" && say "stopped monitor (pid $(cat "$PID_FILE"))"
        rm -f "$PID_FILE"
    else
        say "no monitor running"
    fi
    exit 0
fi

# one instance at a time
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    say "monitor already running (pid $(cat "$PID_FILE"), log: $LOG)"
    exit 0
fi

pids_of() {  # pids_of "pattern"
    pgrep -f "$1" 2>/dev/null | tr '\n' ',' | sed 's/,$//'
}

sample() {
    local ts restarts_dspark restarts_mon back_code llm_up front_code dsp_up tmux_alive
    ts=$(date '+%F %T')
    restarts_dspark=$(systemctl show dspark -p NRestarts --value 2>/dev/null || echo '?')
    restarts_mon=$(systemctl show vaca-monitor -p NRestarts --value 2>/dev/null || echo '?')
    back_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "http://127.0.0.1:3001/api/health" 2>/dev/null)
    llm_up=$(curl -s --max-time 4 "http://127.0.0.1:3001/api/health" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('llm',{}).get('up'))" 2>/dev/null || echo '?')
    front_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "http://127.0.0.1:5173" 2>/dev/null)
    dsp_up=$(curl -s --max-time 4 "http://127.0.0.1:8000/v1/health" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))" 2>/dev/null || echo '?')
    tmux_alive="no"; tmux has-session -t vaca 2>/dev/null && tmux_alive="yes"
    echo "$ts | dspark.restarts=$restarts_dspark mon.restarts=$restarts_mon | backend=$back_code llm=$llm_up front=$front_code dspark=$dsp_up tmux=$tmux_alive | pids dspark=$(pids_of 'dspark_server.py') backend=$(pids_of 'tsx src/index.ts') vite=$(pids_of 'vite --host')" >> "$LOG"
}

echo $$ > "$PID_FILE"
say "starting: sample every ${INTERVAL}s for ${DURATION_H}h → $LOG"
echo "# vaca stability monitor started $(date '+%F %T') — every ${INTERVAL}s for ${DURATION_H}h" >> "$LOG"

samples=$(( DURATION_H * 3600 / INTERVAL ))
for i in $(seq 1 "$samples"); do
    sample
    sleep "$INTERVAL"
done
echo "# vaca stability monitor COMPLETE $(date '+%F %T') — $samples samples" >> "$LOG"
rm -f "$PID_FILE"
say "done — $samples samples logged to $LOG"
