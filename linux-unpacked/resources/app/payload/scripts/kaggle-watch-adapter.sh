#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Watchdog: poll kernel 1 and auto-prepare the rounds-1-2 adapter zip.
# =============================================================================
# Watches  vaca-qlora-rounds-1-2  until it COMPLETES, then downloads its
# Output, extracts the round-2 adapter, and zips the adapter CONTENTS at the
# zip root into a LOCAL artifact:
#
#     training/cloud/rounds12-adapter.zip
#
# That zip is the single artifact both downstream paths consume:
#   • Colab rounds-3-4 (train_vaca_colab_rounds34.ipynb Step 5): upload it —
#     it finds any zip containing an adapter_config.json (flat is fine).
#   • Kaggle kernel 2 (rounds-3-4): upload it as the vaca-rounds12-adapter
#     dataset (kaggle-chain-rounds.sh does this automatically).
#
# Flat layout is deliberate: zipping the adapter CONTENTS at the root (not a
# top-level folder) means kernel 2's `z.extractall(ad_dst)` lands
# adapter_config.json DIRECTLY in /kaggle/working/adapter, matching the
# --load-adapter path.
#
# Usage:
#   bash scripts/kaggle-watch-adapter.sh                 # watch (default, long-running)
#   bash scripts/kaggle-watch-adapter.sh --once          # single status check: prepare if done
#   bash scripts/kaggle-watch-adapter.sh --self-test     # synthetic adapter → verify flat zip (no API)
#   bash scripts/kaggle-watch-adapter.sh --poll-min 300 --max-wait-min 900
#   KAGGLE_USERNAME=stevenawoods bash scripts/kaggle-watch-adapter.sh
#
# Exit codes: 0 = adapter zip ready · 1 = kernel failed/no output · 2 = creds
#             3 = kernel still running (--once) · 4 = self-test failed
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ONCE=0
SELF_TEST=0
POLL_MIN="${POLL_MIN:-600}"       # seconds between status polls (default 10 min)
MAX_WAIT_MIN="${MAX_WAIT_MIN:-900}"  # max minutes to wait for kernel 1 (15 h)

while [ $# -gt 0 ]; do
  case "$1" in
    --once)      ONCE=1 ;;
    --self-test) SELF_TEST=1 ;;
    --poll-min)  shift; POLL_MIN="${1:-600}" ;;
    --max-wait-min) shift; MAX_WAIT_MIN="${1:-900}" ;;
    *) echo "❌ Unknown argument: $1 (expected --once, --self-test, --poll-min N, --max-wait-min N)" >&2; exit 2 ;;
  esac
  shift || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOUD_DIR="$PROJECT_ROOT/training/cloud"
KERNEL1="vaca-qlora-rounds-1-2"
ADAPTER_ZIP="$CLOUD_DIR/rounds12-adapter.zip"

# ─── --self-test: verify the flat zip layout on a synthetic adapter ───────
# Builds a fake adapter dir (adapter_config.json + adapter_model.safetensors),
# zips it the same way the real path does, extracts, and asserts the files
# land at the ROOT (no top-level folder) — exactly what kernel 2 needs.
if [ "$SELF_TEST" = "1" ]; then
  echo "── self-test: flat adapter zip layout (no API calls) ──"
  FAKE="$(mktemp -d)"; FAKE_OUT="$(mktemp -d)"; FAKE_CHK="$(mktemp -d)"
  trap 'rm -rf "$FAKE" "$FAKE_OUT" "$FAKE_CHK"' EXIT
  printf '{"r":8,"lora_alpha":16}' > "$FAKE/adapter_config.json"
  printf 'FAKE-WEIGHTS' > "$FAKE/adapter_model.safetensors"
  (cd "$FAKE" && zip -q -r "$FAKE_OUT/adapter.zip" .)
  python3 -c "import zipfile,sys; zipfile.ZipFile('$FAKE_OUT/adapter.zip').extractall('$FAKE_CHK')"
  for f in adapter_config.json adapter_model.safetensors; do
    if [ ! -f "$FAKE_CHK/$f" ]; then
      echo "❌ self-test FAILED: $f not at zip root (got: $(ls "$FAKE_CHK" | tr '\n' ' '))" >&2
      exit 4
    fi
  done
  if [ -d "$FAKE_CHK/adapter" ]; then
    echo "❌ self-test FAILED: unexpected top-level folder 'adapter/' — zip must be flat." >&2
    exit 4
  fi
  echo "✅ self-test PASS: adapter_config.json + adapter_model.safetensors at zip root (flat)."
  exit 0
fi

# ─── 1. Credentials ────────────────────────────────────────────────────────
KAGGLE_JSON="$HOME/.kaggle/kaggle.json"
if [ ! -f "$KAGGLE_JSON" ] && [ ! -f "$HOME/.kaggle/access_token" ]; then
  echo "❌ No Kaggle credentials found (~/.kaggle/kaggle.json or access_token)." >&2
  exit 2
fi
USERNAME="${KAGGLE_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  USERNAME="$(python3 -c "import json;print(json.load(open('$KAGGLE_JSON'))['username'])" 2>/dev/null || true)"
fi
if [ -z "$USERNAME" ]; then
  echo "❌ Could not determine Kaggle username — set KAGGLE_USERNAME=<name>." >&2
  exit 2
fi
echo "✅ Kaggle username: $USERNAME"

# ─── Status parsing (same robust extractor as kaggle-chain-rounds.sh) ─────
status_word() {
  timeout 30 "$@" 2>/dev/null \
    | grep -oP '(status\s+"[^"]+"|^[A-Za-z]+$)' \
    | head -1 \
    | tr -d '"' \
    | sed 's/.*\.//' \
    | tr '[:upper:]' '[:lower:]' \
    || true
}

# ─── 2. Prepare the adapter zip from a downloaded kernel-1 output dir ─────
# Requires the kernel to have COMPLETED. Downloads output (includes the ~4.4 GB
# GGUF — slow), unpacks wrapper zips, finds results.zip, extracts the round-2
# adapter, and writes the flat adapter zip to $ADAPTER_ZIP.
prepare_adapter() {
  OUT_DIR="$(mktemp -d)"
  # EXIT (not RETURN) so the temp dir is also cleaned when this function
  # terminates via `exit 1` (download failure / no adapter found) — a RETURN
  # trap does NOT fire on exit, leaking the multi-GB download dir.
  trap 'rm -rf "$OUT_DIR"' EXIT
  echo "📥 Downloading kernel 1 output (includes ~4.4 GB GGUF — can take a while)..."
  if ! timeout 1800 kaggle kernels output "$USERNAME/$KERNEL1" -p "$OUT_DIR" 2>&1 | tail -2; then
    echo "❌ Output download failed/timed out — try again later." >&2
    exit 1
  fi
  # Kaggle auto-zips /kaggle/working into kernel-output.zip; the trainer writes
  # out/results.zip inside it. Unpack wrapper zips, then extract results.zip.
  if [ -f "$OUT_DIR/kernel-output.zip" ]; then
    echo "   Unpacking kernel-output.zip ..."
    (cd "$OUT_DIR" && python3 -c "import zipfile; zipfile.ZipFile('kernel-output.zip').extractall('.')")
  fi
  RESULT_ZIP="$(find "$OUT_DIR" -name 'results.zip' | head -1 || true)"
  if [ -n "$RESULT_ZIP" ]; then
    echo "   Extracting $(basename "$(dirname "$RESULT_ZIP")")/results.zip ..."
    (cd "$(dirname "$RESULT_ZIP")" && python3 -c "import zipfile; zipfile.ZipFile('results.zip').extractall('.')")
  fi
  # Find the HIGHEST completed adapter (adapter_roundN with max N) — the v6
  # flow runs ONE round per kernel, so the latest round is what the next run
  # resumes from. Fallback: adapter/ (train_round1.py's copy of the last round).
  LAST="$(find "$OUT_DIR" -type d -name 'adapter_round*' \
    | sed 's/.*adapter_round//' | grep -E '^[0-9]+$' | sort -n | tail -1 || true)"
  ADAPTER_SRC=""
  if [ -n "$LAST" ]; then
    ADAPTER_SRC="$(find "$OUT_DIR" -type d -name "adapter_round$LAST" | head -1 || true)"
  fi
  if [ -z "$ADAPTER_SRC" ]; then
    ADAPTER_SRC="$(find "$OUT_DIR" -type d -name adapter | head -1 || true)"
  fi
  if [ -z "$ADAPTER_SRC" ] || { [ ! -f "$ADAPTER_SRC/adapter_config.json" ] || { [ ! -f "$ADAPTER_SRC/adapter_model.safetensors" ] && [ ! -f "$ADAPTER_SRC/adapter_model.bin" ]; }; }; then
    echo "❌ No usable adapter found in kernel 1 output (results.zip missing or malformed)." >&2
    echo "   Check the Output tab: https://www.kaggle.com/code/$USERNAME/$KERNEL1" >&2
    exit 1
  fi
  echo "✅ Adapter source: ${ADAPTER_SRC##*/}/  ($(ls "$ADAPTER_SRC" | tr '\n' ' '))"
  # Zip the adapter CONTENTS at the zip root (flat — see header comment).
  (cd "$ADAPTER_SRC" && zip -q -r "$ADAPTER_ZIP" .)
  echo "✅ Adapter zip ready: $ADAPTER_ZIP ($(du -h "$ADAPTER_ZIP" | cut -f1))"
}

# ─── 3. Watch loop (or --once single check) ────────────────────────────────
echo "⏳ Watching $USERNAME/$KERNEL1 (polling every ${POLL_MIN}s, max ${MAX_WAIT_MIN}m)..."
START=$(date +%s)
while true; do
  STATUS="$(status_word kaggle kernels status "$USERNAME/$KERNEL1")"
  [ -z "$STATUS" ] && STATUS="unknown"
  echo "  [$(date +%H:%M:%S)] kernel status: $STATUS"
  case "$STATUS" in
    complete|succeeded|success) echo "✅ Kernel 1 finished: $STATUS"; break ;;
    error|failed|canceled)
      echo "❌ Kernel 1 is $STATUS — cannot prepare an adapter from a failed run." >&2
      echo "   Check: https://www.kaggle.com/code/$USERNAME/$KERNEL1" >&2
      exit 1 ;;
    *)
      if [ "$ONCE" = "1" ]; then
        echo "⏳ Kernel 1 is still $STATUS (not complete) — nothing to prepare yet."
        echo "   Re-run this watchdog later (or omit --once to keep watching)."
        exit 3
      fi
      ;;
  esac
  ELAPSED=$(( ($(date +%s) - START) / 60 ))
  if [ "$ELAPSED" -ge "$MAX_WAIT_MIN" ]; then
    echo "❌ Timed out after ${MAX_WAIT_MIN}m — kernel 1 still not done." >&2
    exit 1
  fi
  sleep "$POLL_MIN"
done

# ─── 4. Done ───────────────────────────────────────────────────────────────
prepare_adapter

echo ""
echo "✅ Watchdog complete!"
echo "   Adapter zip : $ADAPTER_ZIP"
echo ""
echo "   Next steps:"
echo "   • Colab rounds-3-4 : upload rounds12-adapter.zip in Step 5 of"
echo "                        train_vaca_colab_rounds34.ipynb (or to Drive)."
echo "   • Kaggle kernel 2  : bash scripts/kaggle-chain-rounds.sh"
echo "                        (auto-uploads this adapter as a dataset + pushes rounds 3-4)."
