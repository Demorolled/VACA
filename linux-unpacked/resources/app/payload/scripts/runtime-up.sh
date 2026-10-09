#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
# runtime-up.sh — VACA runtime orchestrator
# Brings the local AI runtime up in dependency order:
#   1. Ollama  (port 11434) — local model registry + LLM fallback
#   2. DSpark  (port 8000)  — speculative-decoding LLM server (primary 7B target)
#   3. Backend (port 3001)  — Express API; serves frontend/dist, adopts the
#                             running DSpark (its DSPARK_AUTOSTART never spawns
#                             a duplicate).
# Also:
#   ./scripts/runtime-up.sh --status  → report current state (no changes)
#   ./scripts/runtime-up.sh --kill    → stop backend + dspark
# Logs: scripts/dspark.log, scripts/backend.log, scripts/ollama.log
# ═════════════════════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OLLAMA_PORT=11434
DSPARK_PORT="${DSPARK_PORT:-8000}"
BACKEND_PORT="${PORT:-3001}"
DSPARK_LOG="$ROOT/scripts/dspark.log"
BACKEND_LOG="$ROOT/scripts/backend.log"

say()  { printf '\033[1;34m[orchestrator]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✘\033[0m %s\n' "$*"; }

health() { local code; code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null); echo "${code:-000}"; }
is_up()  { [ "$(health "$1")" = "200" ]; }

ollama_models() {
  curl -s --max-time 3 "http://127.0.0.1:${OLLAMA_PORT}/api/tags" 2>/dev/null \
    | python3 -c "import json,sys; [print('   -', m['name']) for m in json.load(sys.stdin).get('models',[])]" 2>/dev/null
}

# ─── status (no side effects) ──────────────────────────────────────────────
status() {
  echo "── VACA runtime status ───────────────────────────────────────────────"
  if is_up "http://127.0.0.1:${OLLAMA_PORT}/api/tags"; then
    ok "Ollama  : http://127.0.0.1:${OLLAMA_PORT}"; ollama_models
  else
    fail "Ollama  : down (port ${OLLAMA_PORT})"
  fi
  if is_up "http://127.0.0.1:${DSPARK_PORT}/v1/models"; then
    local model
    model=$(curl -s --max-time 3 "http://127.0.0.1:${DSPARK_PORT}/v1/models" \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'] if d.get('data') else 'unknown')" 2>/dev/null)
    ok "DSpark  : http://127.0.0.1:${DSPARK_PORT} (model: ${model:-unknown})"
  else
    fail "DSpark  : down (port ${DSPARK_PORT})"
  fi
  if is_up "http://127.0.0.1:${BACKEND_PORT}/api/health"; then
    local h llm_up llm_model
    h=$(curl -s --max-time 3 "http://127.0.0.1:${BACKEND_PORT}/api/health")
    llm_up=$(echo "$h" | python3 -c "import json,sys; print(json.load(sys.stdin).get('llm',{}).get('up'))" 2>/dev/null)
    llm_model=$(echo "$h" | python3 -c "import json,sys; print(json.load(sys.stdin).get('llm',{}).get('model',''))" 2>/dev/null)
    ok "Backend : http://127.0.0.1:${BACKEND_PORT} (llm.up=${llm_up:-?}, model=${llm_model:-?})"
  else
    fail "Backend : down (port ${BACKEND_PORT})"
  fi
  if is_up "http://127.0.0.1:5173"; then
    ok "Frontend: http://127.0.0.1:5173 (vite dev)"
  else
    warn "Frontend: vite dev not running (backend serves frontend/dist instead)"
  fi
}

# ─── ensure ollama ─────────────────────────────────────────────────────────
ensure_ollama() {
  if is_up "http://127.0.0.1:${OLLAMA_PORT}/api/tags"; then
    ok "Ollama already running on ${OLLAMA_PORT}"
    return 0
  fi
  say "Starting Ollama..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active ollama >/dev/null 2>&1; then
    sudo systemctl start ollama 2>/dev/null || true
  fi
  setsid -f ollama serve >"$ROOT/scripts/ollama.log" 2>&1 </dev/null || nohup ollama serve >"$ROOT/scripts/ollama.log" 2>&1 &
  for i in $(seq 1 20); do
    is_up "http://127.0.0.1:${OLLAMA_PORT}/api/tags" && { ok "Ollama up (~${i}s)"; return 0; }
    sleep 1
  done
  fail "Ollama failed to start — tail scripts/ollama.log"
  return 1
}

# ─── ensure dspark ─────────────────────────────────────────────────────────
ensure_dspark() {
  if is_up "http://127.0.0.1:${DSPARK_PORT}/v1/models"; then
    ok "DSpark already running on ${DSPARK_PORT}"
    return 0
  fi
  say "Starting DSpark (qwen2.5-7b target) — first model load can take 30-60s..."
  # setsid -f fully detaches into a new session so the process survives the
  # caller's shell (and any process-group cleanup of the launching shell).
  if command -v setsid >/dev/null 2>&1; then
    DSPARK_DRAFT_MODE="${DSPARK_DRAFT_MODE:-none}" setsid -f "$ROOT/scripts/start-dspark.sh" --background </dev/null >/dev/null 2>&1 || true
  else
    DSPARK_DRAFT_MODE="${DSPARK_DRAFT_MODE:-none}" "$ROOT/scripts/start-dspark.sh" --background </dev/null >/dev/null 2>&1 || true
  fi
  for i in $(seq 1 180); do
    if is_up "http://127.0.0.1:${DSPARK_PORT}/v1/models"; then
      ok "DSpark up after ~${i}s on port ${DSPARK_PORT} (log: scripts/dspark.log)"
      return 0
    fi
    sleep 1
  done
  fail "DSpark did not come up in 180s — tail scripts/dspark.log"
  return 1
}

# ─── ensure backend ────────────────────────────────────────────────────────
ensure_backend() {
  if is_up "http://127.0.0.1:${BACKEND_PORT}/api/health"; then
    ok "Backend already running on ${BACKEND_PORT}"
    return 0
  fi
  say "Starting backend on port ${BACKEND_PORT} (log: scripts/backend.log)..."
  # Run through tsx: the source mixes extensionless and .js imports, so the
  # compiled dist/ does not run under plain node. tsx is the supported runner.
  # Clear any stale backend that may still hold the port (mirrors start.sh's
  # kill_existing) so a race can never crash the new instance with EADDRINUSE.
  pkill -f '[d]ist/index.js' 2>/dev/null || true
  pkill -f '[t]sx src/index.ts' 2>/dev/null || true
  sleep 1
  # setsid -f detaches into a new session so the backend survives this shell.
  if command -v setsid >/dev/null 2>&1; then
    (cd "$ROOT/backend" && setsid -f npx tsx src/index.ts >"$BACKEND_LOG" 2>&1 </dev/null &)
  else
    (cd "$ROOT/backend" && nohup npx tsx src/index.ts >"$BACKEND_LOG" 2>&1 </dev/null &)
  fi
  for i in $(seq 1 90); do
    if is_up "http://127.0.0.1:${BACKEND_PORT}/api/health"; then
      ok "Backend up after ~${i}s on port ${BACKEND_PORT}"
      return 0
    fi
    sleep 1
  done
  fail "Backend failed to start — tail scripts/backend.log and backend/crash.log"
  return 1
}

# ─── kill ──────────────────────────────────────────────────────────────────
kill_all() {
  say "Stopping backend + dspark..."
  # [t]sx bracket trick: the pattern must never match this shell's own cmdline.
  pkill -f '[d]ist/index.js' 2>/dev/null || true
  pkill -f '[t]sx src/index.ts' 2>/dev/null || true
  [ -f "$ROOT/scripts/server.pid" ] && kill "$(cat "$ROOT/scripts/server.pid")" 2>/dev/null || true
  "$ROOT/scripts/start-dspark.sh" --stop >/dev/null 2>&1 || true
  sleep 2
  status
}

case "${1:-up}" in
  --status|-s) status ;;
  --kill|-k)   kill_all ;;
  *)           ensure_ollama && ensure_dspark && ensure_backend
               echo
               status ;;
esac
