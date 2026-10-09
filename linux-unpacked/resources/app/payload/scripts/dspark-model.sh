#!/usr/bin/env bash
# dspark-model.sh — switch the agent's dspark server (:8000) between models.
#
# dspark serves ONE model at a time, read from scripts/dspark-target.env at
# startup. This tool rewrites that one line and restarts dspark — the
# endpoint (:8000) and every client (VACA backend, qwen terminal, trainer
# scripts) stay untouched; only the loaded model changes.
#
# Any target dspark itself accepts works:
#   • absolute path to a GGUF   (models you modify OUTSIDE ollama)
#   • ollama model name         (models pulled/created INSIDE ollama)
#
# Run ON the agent (llmlab@192.168.1.234):
#   ./dspark-model.sh                 # interactive picker
#   ./dspark-model.sh list            # what can be switched to
#   ./dspark-model.sh use <target>    # switch now
#   ./dspark-model.sh current         # what's loaded right now
#   ./dspark-model.sh rollback        # back to the previous model
#   ./dspark-model.sh wait            # block until healthy (30-90s)
#
# VRAM note: 3× RTX 3060 12 GB. The 14B Q4 (~9 GB) and 12B (~7 GB) fit
# alongside nothing else; the 27B (16 GB) and 35B (21 GB) spill to CPU RAM
# via llama.cpp offload — they run, but slower. Don't expect two big models
# resident at once; dspark is a single-model server.

set -u
# project root (same anchor as start-dspark.sh, so all scripts/ paths align)
cd "$(dirname "$0")/.."

ENV_FILE="scripts/dspark-target.env"
LOG_FILE="scripts/dspark.log"
PORT="${DSPARK_PORT:-8000}"

# ---- candidate registry ------------------------------------------------
# label|source|ref|size|note          source: file | ollama
declare -a CANDIDATES=(
  "R20 14B (modified)|file|$HOME/Desktop/visual-ai-architect/models/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf|8.4G|VACA tuned, current dspark default"
  "Qwen3.8 27B|file|$HOME/Desktop/visual-ai-architect/models/Qwen3.8-27B-Q4_K_M.gguf|16G|qwen terminal model, spills to RAM"
  "gemma-4 12B|file|$HOME/Desktop/visual-ai-architect/models/gemma4-q4/gemma-4-12B-it-abliterated-uncensored.Q4_K_M.gguf|6.9G|fastest big switch"
  "ornith 35B Q3|file|$HOME/Desktop/visual-ai-architect/models/ornith-35b.Q3_K_M.gguf|16G|spills to RAM"
  "ornith 35B Q4|file|$HOME/Desktop/visual-ai-architect/models/ornith-35b.Q4_0.gguf|19G|spills to RAM"
  "vaca-r40|ollama|vaca-r40:latest|15.7G|newest VACA round in ollama"
  "vaca-r38|ollama|vaca-r38:latest|15.7G|previous VACA round"
  "vaca-r36|ollama|vaca-r36:latest|15.7G|older VACA round"
  "ornith:35b|ollama|ornith:35b|21.2G|ornith in ollama"
  "qwen2.5-coder 14B|ollama|qwen2.5-coder:14b|9.0G|stock coder 14B"
  "qwen2.5 7B|ollama|qwen2.5:7b-instruct|4.7G|fast daily driver"
  "qwen2.5vl 7B|ollama|qwen2.5vl:7b|6.0G|vision model"
  "qwen2.5 3B|ollama|qwen2.5:3b|1.9G|tiny + fast"
)

say()  { printf '%s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---- helpers -----------------------------------------------------------
current_target() {
  [ -f "$ENV_FILE" ] && grep -oP '(?<=^DSPARK_TARGET=).*' "$ENV_FILE" | tail -1
}

dspark_pid()      { cat scripts/dspark.pid 2>/dev/null || pgrep -f dspark_server.py | head -1; }
dspark_running()  { curl -s -m 3 "http://127.0.0.1:${PORT}/v1/health" >/dev/null 2>&1; }

wait_healthy() {
  local waited=0
  while [ $waited -lt 150 ]; do
    if dspark_running; then
      say "✅ dspark healthy on :${PORT} — $(current_model_label)"
      return 0
    fi
    sleep 5; waited=$((waited+5)); printf '.'
  done
  say ""; say "⚠ not healthy after ${waited}s — check: tail -40 $LOG_FILE"
  return 1
}

current_model_label() {
  curl -s -m 3 "http://127.0.0.1:${PORT}/v1/health" | python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("model","?"))' 2>/dev/null || echo "?"
}

write_env() {
  local target="$1"
  mkdir -p scripts
  printf 'DSPARK_TARGET=%s\n' "$target" > "$ENV_FILE"
}

restart_dspark() {
  say "── restarting dspark..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet dspark 2>/dev/null; then
    sudo systemctl restart dspark
  else
    # not running under systemd — use the project launcher
    bash scripts/start-dspark.sh --stop >/dev/null 2>&1 || true
    bash scripts/start-dspark.sh --background
  fi
}

# ---- commands ----------------------------------------------------------
cmd_list() {
  say "Switchable models on this agent (dspark :${PORT}, one at a time):"
  local i=1
  for c in "${CANDIDATES[@]}"; do
    IFS='|' read -r label source ref size note <<< "$c"
    cur=""
    [ "$ref" = "$(current_target)" ] && cur="  ← current"
    printf '  %2d) %-20s %-7s %-6s %s%s\n' "$i" "$label" "$source" "$size" "$note" "$cur"
    i=$((i+1))
  done
  say ""
  say "Any other ollama model:  ./dspark-model.sh use <name>:<tag>"
  say "Any other GGUF file:     ./dspark-model.sh use /abs/path/model.gguf"
}

cmd_current() {
  local t; t="$(current_target)"
  say "env file : ${ENV_FILE}"
  say "target   : ${t:-<unset>}"
  if dspark_running; then
    say "loaded   : $(current_model_label)  (healthy on :${PORT})"
  else
    say "loaded   : (dspark not responding — systemctl status dspark)"
  fi
}

resolve_use() {
  # $1 = user arg (number from list, ollama name, or gguf path)
  local arg="$1"
  case "$arg" in
    ''|*[!0-9]*) ;;
    *) # numeric → registry lookup (1-based)
      if [ "$arg" -ge 1 ] && [ "$arg" -le ${#CANDIDATES[@]} ]; then
        IFS='|' read -r label source ref size note <<< "${CANDIDATES[$((arg-1))]}"
        echo "$ref"; return
      fi
      ;;
  esac
  echo "$arg"   # pass through: ollama name or gguf path, dspark resolves both
}

validate() {
  local target="$1" found=""
  case "$target" in
    /*) # file: must exist
      [ -f "$target" ] || die "GGUF not found: $target"
      ;;
    *) # ollama: must exist in tags
      curl -s -m 3 http://127.0.0.1:11434/api/tags \
        | grep -q "\"name\":\"${target}\"" || die "not an ollama model here: $target (see ./dspark-model.sh list)"
      ;;
  esac
}

cmd_use() {
  local target; target="$(resolve_use "${1:-}")"
  [ -n "$target" ] || die "usage: ./dspark-model.sh use <n|ollama-name|/path.gguf>   (./dspark-model.sh list)"
  validate "$target"

  local prev; prev="$(current_target)"
  say "── switching: $(basename "${prev:-unset}") → ${target}"
  write_env "$target"

  # remember previous for rollback
  printf '%s\n' "$prev" > scripts/.dspark-prev-target

  # free VRAM first if ollama holds a loaded model
  curl -s -m 3 http://127.0.0.1:11434/api/ps | grep -q '"name"' && \
    say "   (ollama has a model resident — 'ollama stop <name>' frees VRAM if the switch OOMs)"

  restart_dspark
  say "── waiting for model load (30-90s typical, more for 27B/35B)..."
  wait_healthy || die "switch failed — rollback: ./dspark-model.sh rollback"
}

cmd_rollback() {
  [ -f scripts/.dspark-prev-target ] || die "no previous target saved"
  local prev; prev="$(cat scripts/.dspark-prev-target)"
  [ -n "$prev" ] || die "previous target empty"
  say "── rolling back to: $prev"
  write_env "$prev"
  restart_dspark
  wait_healthy || die "rollback failed"
}

cmd_wait() { wait_healthy; }

# ---- interactive picker ------------------------------------------------
picker() {
  cmd_list
  say ""
  printf 'Switch to [1-%d, name, path, or Enter to cancel]: ' "${#CANDIDATES[@]}"
  read -r choice
  [ -n "$choice" ] || { say "cancelled."; exit 0; }
  cmd_use "$choice"
}

case "${1:-}" in
  "")         picker ;;
  list)       cmd_list ;;
  current)    cmd_current ;;
  use)        shift; cmd_use "${1:-}" ;;
  rollback)   cmd_rollback ;;
  wait)       cmd_wait ;;
  *)          die "usage: dspark-model.sh {list|use <target>|current|rollback|wait}" ;;
esac
