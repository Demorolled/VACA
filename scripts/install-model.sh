#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install-model.sh — fetch the LLM, separately from the app
# =============================================================================
# The model weights are NOT in this repo and NOT in the release artifacts.
# They are tens of GB, they are licensed separately from this app, and they
# change on their own schedule — so they are installed here, once per machine.
#
# Veronica is pinned to a single Qwen2.5 14B model. There are two ways to get
# one, and they give different models:
#
#   --base   (default)
#       `ollama pull qwen2.5-coder:14b` — the public upstream model. This is the
#       name the shipped build defaults to, so nothing else has to be changed.
#
#   --tuned
#       The VACA-tuned Qwen2.5-Coder-14B-Instruct-Uncensored, round 20 Q4_K_M.
#       It is the model this build was actually evaluated against: an uncensored
#       Qwen2.5-Coder-14B base (BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored)
#       with the VACA LoRA rounds merged in, quantised to Q4_K_M (~9.0 GB).
#       It answers to a bare prompt template — `TEMPLATE {{ .Prompt }}` — which
#       is what the fine-tune was trained on, so the template below is not
#       cosmetic and must not be "helpfully" upgraded to a chat template.
#       The weights have to come from somewhere: pass --gguf-url (Hugging Face,
#       a mirror, your own host) or --gguf-path (already on disk).
#
# Usage
#   ./scripts/install-model.sh
#   ./scripts/install-model.sh --tuned --gguf-url https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf
#   ./scripts/install-model.sh --tuned --gguf-path /mnt/models/vaca-r20.Q4_K_M.gguf
#   ./scripts/install-model.sh --dry-run --tuned --gguf-path /tmp/x.gguf
#
# Options
#   --base | --tuned     which model to install (default: base)
#   --gguf-url URL       direct download URL for the tuned GGUF (default: TUNED_GGUF_URL, if set)
#   --gguf-path FILE     use an existing GGUF instead of downloading
#   --name NAME          Ollama model name to create/verify (default: per mode)
#   --endpoint URL       OpenAI-compatible base URL (default: http://127.0.0.1:11434/v1)
#   --cache DIR          where a downloaded GGUF is kept (default: ~/.cache/veronica/models)
#   --min-gb N           refuse a GGUF smaller than N GB (default: 8, guards truncation)
#   --skip-verify        create/pull only; do not ask the model to generate
#   --dry-run            print the plan (Modelfile, commands) and change nothing
#   -h | --help
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODE="base"
GGUF_URL=""
GGUF_PATH=""
NAME=""
ENDPOINT="http://127.0.0.1:11434/v1"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/veronica/models"
MIN_GB=8
SKIP_VERIFY=0
DRY_RUN=0

BASE_MODEL="qwen2.5-coder:14b"
TUNED_MODEL="vaca-r20-q4"
# The base the VACA rounds were trained on. Documented so the tuned weights can
# be reproduced or re-obtained if the hosted copy disappears.
TUNED_BASE_HF="BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"

# Where the tuned GGUF is hosted. This is the ONE place to change it: set it and
# `--tuned` works with no flags for everyone, and the README and release notes
# have a canonical URL to point at. Empty means "not published yet" — `--tuned`
# then explains itself rather than failing mid-download on a 404.
TUNED_GGUF_URL="https://huggingface.co/demorolled/veronica-r20-q4-GGUF/resolve/main/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf"

# Print every leading comment line except the shebang, so the help text cannot
# drift out of sync with a hardcoded line range.
usage() {
  awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"
  exit "${1:-0}"
}

die()  { printf '\n✗ %s\n' "$*" >&2; exit 1; }
say()  { printf '%s\n' "$*"; }
step() { printf '\n── %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --base)      MODE="base" ;;
    --tuned)     MODE="tuned" ;;
    --gguf-url)  GGUF_URL="${2:?--gguf-url needs a URL}"; shift ;;
    --gguf-path) GGUF_PATH="${2:?--gguf-path needs a file}"; shift ;;
    --name)      NAME="${2:?--name needs a value}"; shift ;;
    --endpoint)  ENDPOINT="${2:?--endpoint needs a URL}"; shift ;;
    --cache)     CACHE_DIR="${2:?--cache needs a directory}"; shift ;;
    --min-gb)    MIN_GB="${2:?--min-gb needs a number}"; shift ;;
    --skip-verify) SKIP_VERIFY=1 ;;
    --dry-run)   DRY_RUN=1 ;;
    -h|--help)   usage 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

[ -n "$NAME" ] || { [ "$MODE" = "tuned" ] && NAME="$TUNED_MODEL" || NAME="$BASE_MODEL"; }
case "$NAME" in
  # Model names go straight into a JSON body and an ollama CLI argument; keep
  # them to what Ollama itself accepts rather than quoting our way out of it.
  *[!A-Za-z0-9._:-]*|'') die "unsafe or empty model name: $NAME" ;;
esac

OLLAMA_HOST_URL="${ENDPOINT%/v1}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL%/}"

need() { command -v "$1" >/dev/null 2>&1 || die "$1 not found${2:+ — $2}"; }
have() { command -v "$1" >/dev/null 2>&1; }

# Endpoint or CLI? The Ollama CLI talks to whatever OLLAMA_HOST points at, while
# --endpoint is what the app is configured with. Keep them from silently
# disagreeing: warn if the CLI's target does not match the endpoint we verify.
effective_cli_host() { printf '%s' "${OLLAMA_HOST:-http://127.0.0.1:11434}"; }

preflight() {
  step "preflight"
  need ollama "install it first: https://ollama.com/download"
  have curl || die "curl not found — needed to verify the model answers"

  local cli_host; cli_host="$(effective_cli_host)"
  if [ "$cli_host" != "$OLLAMA_HOST_URL" ]; then
    say "⚠  the ollama CLI targets $cli_host but --endpoint is $OLLAMA_HOST_URL"
    say "   'ollama create/pull' will act on the CLI's server; verification uses --endpoint."
  fi

  if ! curl -fsS --max-time 5 "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
    say "✗ no Ollama server answering at $OLLAMA_HOST_URL"
    say "  start one:  ollama serve &"
    say "  remote box: pass --endpoint http://<host>:11434/v1"
    exit 1
  fi
  say "✓ ollama CLI: $(ollama --version 2>/dev/null | head -1)"
  say "✓ server $OLLAMA_HOST_URL is answering"
  say "  mode: $MODE   model name: $NAME   app endpoint: $ENDPOINT"

  local free_kb free_gb
  free_kb="$(df -Pk "${CACHE_DIR}" 2>/dev/null | awk 'NR==2{print $4}' || df -Pk / | awk 'NR==2{print $4}')"
  free_gb=$(( ${free_kb:-0} / 1024 / 1024 ))
  if [ "$MODE" = "tuned" ]; then
    say "  $free_gb GB free where I would stage the GGUF (want ~10 GB for the file + Ollama's copy)"
  else
    say "  $free_gb GB free (~9 GB needed by the pulled model)"
  fi
}

# ── the tuned GGUF ───────────────────────────────────────────────────────────
# Sets GGUF. Deliberately not a "print the path" function: the progress messages
# below go to stdout, so capturing the output would fold them into the path.
# `FROM` also has to be ABSOLUTE — Ollama parses a relative one as a model
# reference and fails with a bare "invalid model name", which reads like a bad
# target name rather than a bad FROM.
resolve_gguf() {
  if [ -n "$GGUF_PATH" ]; then
    [ -f "$GGUF_PATH" ] || die "--gguf-path does not exist: $GGUF_PATH"
    GGUF="$(cd "$(dirname "$GGUF_PATH")" && pwd)/$(basename "$GGUF_PATH")"
    return
  fi
  # No flag given: fall back to the project's hosted copy, if there is one.
  if [ -z "$GGUF_URL" ]; then
    GGUF_URL="$TUNED_GGUF_URL"
  fi

  if [ -z "$GGUF_URL" ]; then
    cat >&2 <<EOF

✗ --tuned needs the tuned weights, and this project has not published them.

  The VACA R20 Q4_K_M GGUF is a ~9 GB fine-tune of
  $TUNED_BASE_HF
  with the VACA LoRA rounds merged and quantised. Point the script at it:

      --gguf-url  https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf
      --gguf-path /path/to/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf

  If you host your own copy and want the bare '--tuned' to work for everyone,
  set TUNED_GGUF_URL near the top of this script.

  If you only need a working model and do not need the VACA tuning, use --base:
      ./scripts/install-model.sh --base

EOF
    exit 1
  fi

  local fname dest
  fname="$(basename "${GGUF_URL%%\?*}")"
  [ -n "$fname" ] || fname="vaca-r20-q4.gguf"
  dest="$CACHE_DIR/$fname"
  GGUF="$dest"

  if [ "$DRY_RUN" = 1 ]; then
    say "would download $GGUF_URL"
    say "            -> $dest"
    return
  fi

  mkdir -p "$CACHE_DIR"
  need curl
  if [ -s "$dest" ]; then
    say "✓ reusing $dest ($(du -hL "$dest" | cut -f1)) — resuming if incomplete"
  fi
  say "downloading → $dest"
  # -C - resumes a partial file, so a dropped connection does not cost 9 GB.
  if ! curl -fL --retry 3 --retry-delay 5 -C - -o "$dest" "$GGUF_URL"; then
    curl -fL --retry 3 --retry-delay 5 -o "$dest" "$GGUF_URL" \
      || die "download failed: $GGUF_URL"
  fi
}

# Size in bytes of a file, FOLLOWING symlinks.
# GNU stat without -L reports the size of the link itself, so a GGUF that is a
# symlink to another disk — the normal way to keep 9 GB off your root volume —
# measures as 110 bytes and gets rejected as truncated.
file_bytes() {
  local f="$1"
  stat -L -c %s "$f" 2>/dev/null \
    || stat -L -f %z "$f" 2>/dev/null \
    || stat -c %s "$f" 2>/dev/null \
    || stat -f %z "$f" 2>/dev/null \
    || die "cannot stat $f"
}

check_gguf_size() {
  local file="$1" bytes min_bytes human
  [ -f "$file" ] || die "GGUF missing: $file"
  bytes="$(file_bytes "$file")"
  min_bytes=$(( MIN_GB * 1000 * 1000 * 1000 ))
  human="$(awk -v b="$bytes" 'BEGIN{printf "%.2f GB", b/1e9}') (${bytes} bytes)"
  if [ "$bytes" -lt "$min_bytes" ]; then
    die "$(basename "$file") is only $human; expected ≥ ${MIN_GB} GB.
   A Q4_K_M of this 14B model is ~9 GB, so a file this small is truncated or
   the wrong artefact. Override with --min-gb if you know it is right."
  fi
  say "✓ $(basename "$file"): $human"
}

write_modelfile() {
  local gguf_abs="$1" dir="$2"
  mkdir -p "$dir"
  MODEFILE="$dir/Modelfile"
  cat > "$MODEFILE" <<EOF
FROM $gguf_abs
TEMPLATE {{ .Prompt }}
PARAMETER num_ctx 16384
PARAMETER temperature 0.7
PARAMETER top_p 0.9
EOF
}

# ── verification ─────────────────────────────────────────────────────────────
verify_name_listed() {
  local listing
  listing="$(curl -fsS --max-time 10 "$OLLAMA_HOST_URL/api/tags" || true)"
  if have jq; then
    printf '%s' "$listing" | jq -e --arg n "$NAME" \
      '(.models // []) | any(.name == $n or .name == ($n + ":latest"))' >/dev/null 2>&1 \
      || return 1
  else
    printf '%s' "$listing" | grep -q "\"$NAME" || return 1
  fi
  return 0
}

verify_generates() {
  local payload reply code body text err
  say "asking the model to generate (this is the real test — a listed name can still be broken)"
  payload="{\"model\":\"$NAME\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"max_tokens\":16,\"temperature\":0}"
  # Deliberately no curl -f: an HTTP error still carries the server's own
  # explanation in the body, and "model not found" is the single most useful
  # thing this script can tell someone.
  reply="$(curl -sS --max-time 180 -w '\n__HTTP__%{http_code}' \
             -H 'Content-Type: application/json' \
             -d "$payload" "$ENDPOINT/chat/completions" 2>/dev/null || true)"
  code="${reply##*__HTTP__}"
  body="${reply%"__HTTP__$code"}"
  # curl's -w block always ends with the \n we asked for; drop exactly that one.
  body="${body%?}"
  if [ -z "$code" ]; then
    say "✗ $ENDPOINT/chat/completions did not answer — is the endpoint reachable from here?"
    return 1
  fi
  if [ "$code" != "200" ]; then
    say "✗ $ENDPOINT returned HTTP $code"
    if have jq; then
      err="$(printf '%s' "$body" | jq -r '.error.message? // .error? // empty' 2>/dev/null || true)"
      if [ -n "$err" ]; then say "  server said: $err"; fi
    fi
    if [ -n "$body" ]; then
      say "  body: $(printf '%s' "$body" | tr -d '\n' | head -c 300)"
    fi
    return 1
  fi
  reply="$body"
  if have jq; then
    local text err
    err="$(printf '%s' "$reply" | jq -r '.error.message? // empty' 2>/dev/null || true)"
    text="$(printf '%s' "$reply" | jq -r '.choices[0].message.content? // empty' 2>/dev/null || true)"
    if [ -n "$err" ]; then say "✗ server said: $err"; return 1; fi
    if [ -z "$text" ]; then say "✗ no content in response: $(printf '%s' "$reply" | head -c 200)"; return 1; fi
    say "✓ $NAME answered: $(printf '%s' "$text" | tr -d '\n' | head -c 60)"
  else
    say "✓ $NAME answered (jq not installed, raw: $(printf '%s' "$reply" | head -c 160))"
  fi
  return 0
}

print_app_config() {
  step "point the app at it"
  cat <<EOF
  Settings (Ctrl+,) ▸ Model
    LLM endpoint : $ENDPOINT
    Model        : $NAME
    then "Save & restart".
EOF
  if [ "$NAME" = "$BASE_MODEL" ]; then
    cat <<EOF

  $NAME is the shipped default, so the app is already pointed at it —
  open Settings only if this server is not on 127.0.0.1 or is on another port.
EOF
  else
    cat <<EOF

  The shipped default is $BASE_MODEL, so this is a change: put $NAME in
  the Model field. Leave it and the app asks the server for a model that is not
  there, and generation fails — /health reports llm.up:false.
EOF
  fi
  cat <<EOF

  Remote server instead of localhost? Put its URL in the endpoint field, e.g.
  http://192.168.1.234:11434/v1 — the same model has to exist there.
EOF
}

# ── main ─────────────────────────────────────────────────────────────────────
say "Veronica — model installer"

if [ "$MODE" = "base" ]; then
  [ "$DRY_RUN" = 1 ] || preflight
  step "pull $NAME"
  if [ "$DRY_RUN" = 1 ]; then
    say "would run: ollama pull $NAME        (~9 GB download on first run)"
  else
    ollama pull "$NAME" || die "ollama pull failed"
  fi
else
  [ "$DRY_RUN" = 1 ] || preflight
  step "resolve tuned GGUF"
  GGUF=""
  MODEFILE=""
  resolve_gguf
  if [ "$DRY_RUN" = 1 ]; then
    say "would check size ≥ ${MIN_GB} GB"
  else
    check_gguf_size "$GGUF"
  fi

  if [ "$DRY_RUN" = 0 ]; then
    step "write Modelfile"
    write_modelfile "$GGUF" "$CACHE_DIR"
    say "✓ $MODEFILE"
    sed 's/^/    /' "$MODEFILE"
    step "ollama create $NAME"
    ollama create "$NAME" -f "$MODEFILE" || die "ollama create failed"
  else
    say "would write $CACHE_DIR/Modelfile:"
    printf 'FROM %s\nTEMPLATE {{ .Prompt }}\nPARAMETER num_ctx 16384\nPARAMETER temperature 0.7\nPARAMETER top_p 0.9\n' "$GGUF" | sed 's/^/    /'
    say "would run: ollama create $NAME -f $CACHE_DIR/Modelfile"
  fi
fi

if [ "$DRY_RUN" = 1 ]; then
  say ""
  say "dry run — nothing was pulled, created or downloaded."
  print_app_config
  exit 0
fi

if [ "$SKIP_VERIFY" = 0 ]; then
  step "verify"
  verify_name_listed || die "$NAME is not listed by the server at $OLLAMA_HOST_URL after install"
  say "✓ $NAME is listed"
  if ! verify_generates; then
    printf '\n' >&2
    say "✗ the model is installed but did not produce a completion." >&2
    if [ "$MODE" = "tuned" ]; then
      say "  A tuned model with a wrong template still loads and still fails like this." >&2
      say "  Check that the Modelfile kept 'TEMPLATE {{ .Prompt }}' verbatim." >&2
    fi
    exit 1
  fi
fi

print_app_config
say ""
say "✓ done."
