#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# vaca-start.sh — start the VACA app on THIS machine's desktop.
#
# Built for the RD-Desktop setup: VACA runs on the 2nd computer (the GPU
# box) inside its VNC virtual desktop, and you watch/control it from the
# control computer over VNC. This script brings the whole app up there:
#
#   1. runs the runtime orchestrator (scripts/runtime-up.sh) which starts
#      Ollama + DSpark + the backend (:3001, serves the built frontend),
#   2. with --frontend: also starts the Vite dev server (:5173, hot reload)
#      in a second tmux window — the "backend + frontend" mode,
#   3. opens a browser window on the VNC desktop pointed at the app, so it
#      is already on screen when you connect from the other computer.
#
# Everything is started detached (setsid/nohup), so the app keeps running
# when the VNC viewer disconnects, and even when the SSH session that
# triggered it ends. A tmux session "vaca" is kept alive as a live log
# handle (tmux attach -t vaca) and as a marker that VACA is up.
#
# Usage:
#   bash scripts/vaca-start.sh              start backend (idempotent)
#   bash scripts/vaca-start.sh --frontend   start backend + frontend (vite :5173)
#   bash scripts/vaca-start.sh --restart    stop, then start fresh
#   bash scripts/vaca-start.sh --stop       stop backend + dspark (+ vite)
#   bash scripts/vaca-start.sh --status     report what's running
#   bash scripts/vaca-start.sh --session    (internal) tmux session payload
#
# Env overrides:
#   VACA_ROOT     project dir (default: auto-detected repo root)
#   VACA_PORT     backend port (default 3001)
#   VACA_FRONTEND 1 = also start the vite dev frontend (same as --frontend)
#   NO_BROWSER=1  don't open the browser window on the desktop
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${VACA_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PORT="${VACA_PORT:-3001}"
FRONTEND_PORT=5173
SESSION="vaca"
LOG_DIR="$ROOT/scripts"

say()  { printf '\033[1;34m[vaca-start]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✘\033[0m %s\n' "$*"; }

backend_health() { local code; code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null); echo "${code:-000}"; }
backend_up() { [ "$(backend_health)" = "200" ]; }
frontend_up() { curl -s -o /dev/null --max-time 3 "http://127.0.0.1:${FRONTEND_PORT}" 2>/dev/null; }

session_alive() { tmux has-session -t "$SESSION" 2>/dev/null; }

# ─── find the desktop (VNC) display to open the browser on ────────────────
detect_display() {
    [ -n "${DISPLAY:-}" ] && return 0
    local d
    # Virtual desktop (TigerVNC) or mirrored console session (x11vnc)
    d=$(pgrep -af 'Xvnc|Xtigervnc' 2>/dev/null | grep -oE ':[0-9]+' | head -1 || true)
    [ -z "$d" ] && d=$(pgrep -af 'x11vnc' 2>/dev/null | grep -oE ':[0-9]+' | head -1 || true)
    [ -z "$d" ] && d=":0"
    export DISPLAY="$d"
    if [ -z "${XAUTHORITY:-}" ] && [ -f "$HOME/.Xauthority" ]; then
        export XAUTHORITY="$HOME/.Xauthority"
    fi
    return 0
}

# ─── open the app in the desktop's browser (detached) ─────────────────────
open_browser() {
    [ "${NO_BROWSER:-0}" = "1" ] && return 0
    local url="${1:-http://localhost:${PORT}}"
    detect_display
    local b=""
    for cand in xdg-open firefox chromium chromium-browser google-chrome brave-browser; do
        if command -v "$cand" >/dev/null 2>&1; then
            b="$cand"
            break
        fi
    done
    if [ -z "$b" ]; then
        warn "no browser found on this desktop — open ${url} (or http://<this-ip>:${PORT}) manually"
        return 0
    fi
    say "opening ${url} in ${b} on display ${DISPLAY:-?}..."
    nohup "$b" "$url" >/dev/null 2>&1 &
    return 0
}

# ─── ensure the built frontend exists (backend serves frontend/dist) ──────
ensure_frontend_build() {
    if [ -f "$ROOT/frontend/dist/index.html" ]; then
        return 0
    fi
    say "no frontend build yet — building once (backend serves frontend/dist)..."
    if [ ! -d "$ROOT/node_modules" ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
        warn "node_modules missing — run 'npm install' in $ROOT first"
        return 1
    fi
    (cd "$ROOT" && npm run build --workspace=frontend >"$LOG_DIR/vaca-app-build.log" 2>&1) || {
        fail "frontend build failed — tail $LOG_DIR/vaca-app-build.log"
        return 1
    }
    ok "frontend built"
}

# True if something listens on :5173 on a non-loopback address (LAN-reachable).
frontend_lan_bound() {
    ss -tln 2>/dev/null | awk '{print $4}' | grep -E '^(\*|0\.0\.0\.0|\[::\]):5173$' | grep -q .
}

# ─── start the vite dev frontend in a second tmux window ──────────────────
start_frontend_window() {
    if frontend_up; then
        if frontend_lan_bound; then
            ok "frontend dev server already running on :${FRONTEND_PORT} — adopting it"
            return 0
        fi
        warn "existing vite on :${FRONTEND_PORT} is bound to localhost only — restarting it with --host (LAN-reachable)"
        pkill -f 'vite' 2>/dev/null || true
        sleep 1
    fi
    say "starting vite dev frontend on :${FRONTEND_PORT} (tmux window 'front')..."
    # Run the frontend workspace's OWN vite binary, NOT `npx vite`: on npm 9
    # (e.g. the agent) npx resolves the ROOT node_modules/.bin/vite (7.3.5),
    # which breaks @vitejs/plugin-react 6 ("Missing field moduleType" -> blank
    # page). The workspace's .bin has the right 8.0.16. Fall back to npx only
    # if the direct binary is somehow missing.
    local vite_bin="$ROOT/frontend/node_modules/.bin/vite"
    if [ ! -x "$vite_bin" ]; then
        vite_bin="npx vite"
    fi
    tmux new-window -t "$SESSION" -n front \
        "cd '$ROOT/frontend' && $vite_bin --host 2>&1 | tee -a '$LOG_DIR/vite.log'" \
        || { warn "could not create frontend tmux window"; return 1; }
    local i=0
    until frontend_up || [ "$i" -ge 60 ]; do
        i=$((i + 2))
        sleep 2
    done
    if frontend_up; then
        ok "frontend dev server is up on :${FRONTEND_PORT}"
    else
        fail "vite did not come up in 120s — tail $LOG_DIR/vite.log"
    fi
    return 0
}

# ─── tmux session payload: runtime up → wait → browser → live log ─────────
run_session() {
    cd "$ROOT" || exit 1
    # Run the orchestrator in the background: it starts what's missing
    # (ollama/dspark/backend) and its own dspark health wait must not delay
    # the desktop here. The backend is the gate — poll that directly.
    bash scripts/runtime-up.sh >"$LOG_DIR/vaca-runtime.log" 2>&1 &
    say "runtime orchestrator starting (log: $LOG_DIR/vaca-runtime.log)"
    say "waiting for backend health on :${PORT} (first DSpark model load can take 30-120s)..."
    local i=0
    until backend_up || [ "$i" -ge 240 ]; do
        i=$((i + 2))
        sleep 2
    done
    if ! backend_up; then
        fail "backend did not come up in 240s — tail $LOG_DIR/backend.log"
    else
        ok "backend is up — VACA ready"
    fi

    local url="http://localhost:${PORT}"
    if [ "${VACA_FRONTEND:-0}" = "1" ]; then
        start_frontend_window
        if frontend_up; then
            url="http://localhost:${FRONTEND_PORT}"
        fi
    fi
    open_browser "$url"

    # Keep the session alive as a live log handle (tmux attach -t vaca).
    exec tail -f "$LOG_DIR/backend.log"
}

# ─── start ─────────────────────────────────────────────────────────────────
do_start() {
    cd "$ROOT" || exit 1
    if session_alive && backend_up; then
        ok "VACA already running (tmux session '$SESSION', backend on :${PORT})"
        if [ "${VACA_FRONTEND:-0}" = "1" ]; then
            if frontend_up; then
                ok "frontend dev server already up on :${FRONTEND_PORT}"
                open_browser "http://localhost:${FRONTEND_PORT}"
            else
                warn "frontend not running — restart with: $0 --restart --frontend"
            fi
        else
            open_browser "http://localhost:${PORT}"
        fi
        return 0
    fi
    command -v tmux >/dev/null 2>&1 || { fail "tmux not installed — run: sudo apt-get install -y tmux"; return 1; }
    ensure_frontend_build || return 1
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    VACA_FRONTEND="${VACA_FRONTEND:-0}" tmux new-session -d -s "$SESSION" "bash '$SCRIPT_DIR/vaca-start.sh' --session" \
        || { fail "could not create tmux session '$SESSION'"; return 1; }
    say "VACA starting in tmux session '$SESSION' — attach with: tmux attach -t $SESSION"
    say "  backend log:  $LOG_DIR/backend.log"
    say "  frontend log: $LOG_DIR/vite.log"
    return 0
}

# ─── stop ──────────────────────────────────────────────────────────────────
do_stop() {
    cd "$ROOT" || exit 1
    tmux kill-session -t "$SESSION" 2>/dev/null && ok "stopped tmux session '$SESSION' (backend + frontend)" || true
    bash scripts/runtime-up.sh --kill >/dev/null 2>&1
    ok "backend + dspark stopped (browser window left open)"
    return 0
}

# ─── status ────────────────────────────────────────────────────────────────
do_status() {
    cd "$ROOT" || exit 1
    echo "── VACA app status ────────────────────────────────────────────────"
    if session_alive; then
        ok "tmux session '$SESSION': running (attach: tmux attach -t $SESSION)"
        tmux list-windows -t "$SESSION" 2>/dev/null | sed 's/^/    /'
    else
        warn "tmux session '$SESSION': not running"
    fi
    bash scripts/runtime-up.sh --status
    return 0
}

# ─── args: modes + --frontend modifier ────────────────────────────────────
MODE="start"
VACA_FRONTEND="${VACA_FRONTEND:-0}"
for a in "$@"; do
    case "$a" in
        --session)  MODE="session" ;;
        --stop|-k)  MODE="stop" ;;
        --restart)  MODE="restart" ;;
        --status|-s) MODE="status" ;;
        --frontend) VACA_FRONTEND=1 ;;
        start)      MODE="start" ;;
        *) echo "usage: $0 [start|--frontend|--restart|--stop|--status]"; exit 1 ;;
    esac
done

case "$MODE" in
    session) run_session ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 2; do_start ;;
    status)  do_status ;;
    start)   do_start ;;
esac
