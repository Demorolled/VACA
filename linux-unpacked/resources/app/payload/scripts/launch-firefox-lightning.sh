#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Launch a CDP-enabled Firefox pointed at the Lightning AI studio, so we
#  can drive the upload + training from scripts (like the Colab/Kaggle
#  automation). Uses a SEPARATE profile so your existing Firefox is
#  untouched.
#
#  Usage:
#      bash scripts/launch-firefox-lightning.sh
#
#  Then log into Lightning in that window (once). Afterwards:
#      python3 scripts/cdp_lightning.py title
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${CDP_PORT:-9225}"
PROFILE="${FIREFOX_PROFILE:-/tmp/lightning-ff-profile}"
STUDIO_URL="${LIGHTNING_URL:-https://lightning.ai/bigstuff2gs-org/financial-llm-training-project/studios/training-devbox/code}"

mkdir -p "$PROFILE"

if curl -s --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "⚠  Port $PORT already has a CDP endpoint (Firefox already running?)."
  echo "   Just log in / use it, or kill it first: pkill -f 'remote-debugging-port=$PORT'"
  exit 1
fi

echo "🚀 Launching Firefox on port $PORT → $STUDIO_URL"
echo "   Profile: $PROFILE (separate from your normal Firefox)"
nohup firefox --new-instance \
  --profile "$PROFILE" \
  --remote-debugging-port "$PORT" \
  --new-tab "$STUDIO_URL" \
  >/tmp/lightning-ff.log 2>&1 &
echo $! > /tmp/lightning-ff.pid

echo "⏳ Waiting for the CDP endpoint…"
for i in $(seq 1 30); do
  sleep 1
  if curl -s --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "✅ CDP live on port $PORT"
    echo
    echo "Next steps:"
    echo "  1. In the new Firefox window, LOG IN to Lightning (you made this account)."
    echo "  2. Tell me when you're logged in — I'll take over: upload the dataset,"
    echo "     start the 4h-chunked training, and re-connect after each shutdown."
    exit 0
  fi
done
echo "❌ CDP endpoint didn't come up in 30s — check /tmp/lightning-ff.log"
exit 1
