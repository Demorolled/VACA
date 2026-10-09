#!/usr/bin/env bash
# vaca-trainer.sh — start/stop the VACA self-play trainer + live scoreboard.
#
# This is the "button" for the trainer. It works on whichever machine the repo
# checkout lives on, and can drive a different box over ssh when the training
# GPUs aren't local (set TRAIN_HOST=user@host).
#
#   ./scripts/vaca-trainer.sh menu        # interactive menu (what the icon runs)
#   ./scripts/vaca-trainer.sh start       # scoreboard + training round loop
#   ./scripts/vaca-trainer.sh scoreboard  # scoreboard only, opens browser
#   ./scripts/vaca-trainer.sh stop        # stop trainer and scoreboard
#   ./scripts/vaca-trainer.sh status      # what's running
#   ./scripts/vaca-trainer.sh doctor      # GPUs / venv / endpoints check
#
# Everything is logged under training/selfplay/work/.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

WORK="$ROOT/training/selfplay/work"
LOGS="$ROOT/training/selfplay/logs"
PORT="${SCOREBOARD_PORT:-8300}"
TRAIN_HOST="${TRAIN_HOST:-}"           # e.g. homellmlab@192.168.1.234
VENV_PY="$ROOT/llm-training-app/.venv/bin/python"
mkdir -p "$WORK" "$LOGS"

# ── helpers ──────────────────────────────────────────────────────────────────
c_ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_bad()  { printf '\033[31m%s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m%s\033[0m\n' "$*"; }
c_hd()   { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

py() { if [ -x "$VENV_PY" ]; then "$VENV_PY" "$@"; else python3 "$@"; fi; }

# PID-file based checks: `pgrep -f` also matches any unrelated process whose
# command line merely mentions the pattern (including the shell that invoked
# this script), which produced phantom "already running" reports.
PID_DIR="$WORK"

_alive() {  # _alive <pidfile> [must-contain]
  local f="$PID_DIR/$1" pid
  [ -f "$f" ] || return 1
  pid=$(cat "$f" 2>/dev/null)
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if [ -n "${2:-}" ]; then
    tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q "$2" || return 1
  fi
  return 0
}

trainer_pid() { cat "$PID_DIR/trainer.pid" 2>/dev/null; }

sb_running() { _alive scoreboard.pid "scoreboard"; }
or_running() { _alive trainer.pid "orchestrator"; }

open_browser() {
  local url="http://127.0.0.1:$PORT"
  if command -v xdg-open >/dev/null 2>&1; then
    (xdg-open "$url" >/dev/null 2>&1 &) ; echo "opened $url"
  else
    echo "browse to $url"
  fi
}

# ── doctor ───────────────────────────────────────────────────────────────────
doctor() {
  c_hd "hardware"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv,noheader
    local n; n=$(nvidia-smi --list-gpus 2>/dev/null | wc -l)
    echo "cuda gpus visible: $n"
    if [ "$n" -lt 2 ]; then
      c_warn "14B QLoRA wants 2 cards (sharded 4-bit). With $n card(s) expect it to be slow or OOM."
      c_warn "Training runs on the agent box; set TRAIN_HOST to drive it remotely."
    fi
  else
    c_bad "no nvidia-smi — this machine cannot train"
  fi
  c_hd "python env"
  if [ -x "$VENV_PY" ]; then
    py -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),'ngpu',torch.cuda.device_count())" 2>&1 | tail -3
  else
    c_bad "missing $VENV_PY"
  fi
  c_hd "endpoints"
  local student judge
  student=$(py -c "from training.selfplay.config import load_config;print(load_config(None).endpoints.student_url)" 2>/dev/null)
  judge=$(py -c "from training.selfplay.config import load_config;print(load_config(None).endpoints.judge_url)" 2>/dev/null)
  for u in "$student" "$judge"; do
    [ -z "$u" ] && continue
    local hp; hp=$(echo "$u" | sed -E 's#^https?://##; s#/.*$##')
    if timeout 2 bash -c "echo > /dev/tcp/${hp%%:*}/${hp##*:}" 2>/dev/null; then
      c_ok "reachable  $u"
    else
      c_bad "unreachable $u"
    fi
  done
  c_hd "config"
  [ -f "$ROOT/training/selfplay/selfplay.json" ] && c_ok "selfplay.json present" || c_warn "no selfplay.json (run: python3 -m training.selfplay.orchestrator --init-config)"
}

# ── start / stop ─────────────────────────────────────────────────────────────
start_scoreboard() {
  if sb_running; then c_ok "scoreboard already running (port $PORT, pid $(cat "$PID_DIR/scoreboard.pid"))"; return; fi
  nohup python3 -m training.selfplay.scoreboard --port "$PORT" \
    >>"$LOGS/scoreboard.log" 2>&1 &
  echo $! >"$PID_DIR/scoreboard.pid"
  sleep 1.5
  if sb_running; then c_ok "scoreboard started (port $PORT, pid $(cat "$PID_DIR/scoreboard.pid"))";
  else c_bad "scoreboard failed to start — see $LOGS/scoreboard.log"; rm -f "$PID_DIR/scoreboard.pid"; fi
}

start_training() {
  if or_running; then c_ok "trainer already running (pid $(trainer_pid))"; return; fi
  local cmd=(python3 -m training.selfplay.orchestrator)
  if [ -n "$TRAIN_HOST" ]; then
    c_warn "remote mode: running on $TRAIN_HOST"
    nohup ssh -o BatchMode=yes "$TRAIN_HOST" \
      "cd '$ROOT' && nohup ${cmd[*]} >>'$LOGS/orchestrator.log' 2>&1 &" \
      >>"$LOGS/orchestrator.log" 2>&1 &
  else
    nohup "${cmd[@]}" >>"$LOGS/orchestrator.log" 2>&1 &
  fi
  echo $! >"$PID_DIR/trainer.pid"
  sleep 2
  if or_running; then c_ok "trainer started — follow $LOGS/orchestrator.log";
  else c_bad "trainer exited immediately — check $LOGS/orchestrator.log"; rm -f "$PID_DIR/trainer.pid"; fi
}

stop_one() {  # stop_one <pidfile> <label>
  local f="$PID_DIR/$1" pid
  if [ -f "$f" ]; then
    pid=$(cat "$f" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null && c_ok "$2 stopped (pid $pid)"
    else
      echo "$2 not running"
    fi
    rm -f "$f"
  else
    echo "$2 not running"
  fi
}

stop_all() {
  stop_one trainer.pid trainer
  stop_one scoreboard.pid scoreboard
}

status() {
  c_hd "status"
  or_running && c_ok "trainer: running (pid $(trainer_pid))" || echo "trainer: stopped"
  sb_running && c_ok "scoreboard: http://127.0.0.1:$PORT" || echo "scoreboard: stopped"
  [ -f "$WORK/state.json" ] && py -c "
import json;d=json.load(open('$WORK/state.json'))
print('rounds completed:', d.get('completed_rounds'))
for h in (d.get('history') or [])[-3:]:
    print(' ', h)
" 2>/dev/null
}

menu() {
  while true; do
    cat <<EOF

╔══════════════════════════════════════════════╗
║   VACA self-play trainer                     ║
╠══════════════════════════════════════════════╣
║  1) Start trainer + scoreboard               ║
║  2) Scoreboard only (opens browser)          ║
║  3) Status                                   ║
║  4) Doctor (gpus / env / endpoints)          ║
║  5) Stop everything                          ║
║  6) Dry run one round (plan only)            ║
║  q) Quit                                     ║
╚══════════════════════════════════════════════╝
EOF
    read -rp "choice> " ch
    case "$ch" in
      1) start_scoreboard; start_training; open_browser; status ;;
      2) start_scoreboard; open_browser ;;
      3) status ;;
      4) doctor ;;
      5) stop_all ;;
      6) py -m training.selfplay.orchestrator --dry-run --rounds 1 ;;
      q|Q) exit 0 ;;
      *) echo "?" ;;
    esac
  done
}

case "${1:-menu}" in
  start)      start_scoreboard; start_training; open_browser; status ;;
  scoreboard) start_scoreboard; open_browser ;;
  stop)       stop_all ;;
  status)     status ;;
  doctor)     doctor ;;
  dry)        py -m training.selfplay.orchestrator --dry-run --rounds 1 ;;
  menu)       menu ;;
  *)          echo "usage: $0 {menu|start|scoreboard|stop|status|doctor|dry}"; exit 1 ;;
esac
