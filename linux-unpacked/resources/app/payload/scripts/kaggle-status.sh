#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Kaggle VACA kernel status — one-shot helper
# =============================================================================
# Prints the status of both VACA training kernels (rounds 1-2 and rounds 3-4)
# and, for FAILED kernels, downloads the execution log and shows its tail —
# so you can tell at a glance whether cloud training is running, done, or dead
# (and why: e.g. "CUDA: False", "Temporary failure in name resolution").
#
# Notes:
#   - The log download is only performed for error/failed/canceled kernels
#     (that's where the tail is useful). A COMPLETED kernel's output embeds the
#     ~4.4 GB GGUF, so it is NOT auto-downloaded — use --all if you really want
#     it (large/slow), or fetch results.zip via kaggle-chain-rounds.sh.
#   - Read-only: only queries status + downloads small logs.
#
# Usage:
#   bash scripts/kaggle-status.sh                  # status + log tail for errors
#   bash scripts/kaggle-status.sh --all            # also fetch output for non-error kernels
#   bash scripts/kaggle-status.sh --lines 60       # more log lines (default 40)
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-status.sh
#
# Exit codes: 0 = done · 1 = no credentials / API failure
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ALL=0
TAIL_LINES=40
while [ $# -gt 0 ]; do
  case "$1" in
    --all)   ALL=1 ;;
    --lines) shift; TAIL_LINES="${1:-40}" ;;
    --lines=*) TAIL_LINES="${1#*=}" ;;
    *) echo "❌ Unknown argument: $1 (expected --all or --lines N)" >&2; exit 1 ;;
  esac
  shift || true   # tolerate `--lines` as the last arg (already consumed above)
done

KERNELS=(vaca-qlora-rounds-1-2 vaca-qlora-rounds-3-4)

# ─── Credentials (same resolution as kaggle-setup.sh / kaggle-chain-rounds.sh) ─
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or access_token)." >&2
  exit 1
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  USERNAME="$(kaggle config view 2>/dev/null | grep -oP 'username: \K\S+' || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 1
fi

# ─── Status parsing ────────────────────────────────────────────────────────
# '… has status "KernelWorkerStatus.ERROR"' → 'error' (also handles bare words
# and dataset-style 'ready'). Pure stdin filter — pipe the captured status
# output in; no extra API call.
status_word() {
  grep -oP '(status\s+"[^"]+"|^[A-Za-z]+$)' \
    | head -1 \
    | tr -d '"' \
    | sed 's/.*\.//' \
    | tr '[:upper:]' '[:lower:]' \
    || true
}

# Extract the trailing N lines of combined stdout/stderr from Kaggle's
# JSON-stream kernel log (one JSON object per line, "[{"..."," data may contain
# escaped \n).
log_tail() {
  local log="$1" n="$2"
  python3 - "$log" "$n" <<'PYEOF'
import json, sys
log, n = sys.argv[1], int(sys.argv[2])
entries = []
with open(log, errors="ignore") as f:
    for line in f:
        line = line.strip().lstrip("[").lstrip(",")
        if line.startswith("{"):
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
chunks = [e.get("data", "") for e in entries if e.get("data")]
lines = "".join(chunks).splitlines()
print("\n".join(lines[-n:]) if lines else "(log empty)")
PYEOF
}

echo "Kaggle user: $USERNAME"
echo ""

for K in "${KERNELS[@]}"; do
  echo "═══════════════════════════════════════════════════════════"
  echo "Kernel: $K"
  RAW="$(timeout 30 kaggle kernels status "$USERNAME/$K" 2>&1 || true)"
  STATUS="$(printf '%s' "$RAW" | status_word)"
  if [ -z "$STATUS" ]; then
    if printf '%s' "$RAW" | grep -qiE 'denied|cannot access|not found'; then
      echo "  ❌ Not found / not pushed yet (kernel may not exist or is private)"
    else
      echo "  ❓ Unknown status — raw output: $(printf '%s' "$RAW" | head -1)"
    fi
    continue
  fi
  echo "  Status: $STATUS"
  echo "  URL   : https://www.kaggle.com/code/$USERNAME/$K"

  # Fetch + tail the log for failed kernels (or any kernel with --all).
  case "$STATUS" in
    error|failed|canceled) FETCH=1 ;;
    *) [ "$ALL" = "1" ] && FETCH=1 || FETCH=0 ;;
  esac
  if [ "$FETCH" = "1" ]; then
    TMP="$(mktemp -d)"
    echo "  📥 Fetching kernel log..."
    if timeout 120 kaggle kernels output "$USERNAME/$K" -p "$TMP" >/dev/null 2>&1; then
      LOG="$(find "$TMP" -name '*.log' | head -1 || true)"
      if [ -n "$LOG" ] && [ -s "$LOG" ]; then
        echo "  ── log tail (last $TAIL_LINES lines) ──"
        log_tail "$LOG" "$TAIL_LINES" | sed 's/^/    /' || true
      else
        echo "  (no log file in output)"
      fi
    else
      echo "  (could not fetch output — kernel may still be processing)"
    fi
    rm -rf "$TMP"
  fi
  echo ""
done

echo "═══════════════════════════════════════════════════════════"
echo "Done. Complete/errored → see above. Running → check again later."
