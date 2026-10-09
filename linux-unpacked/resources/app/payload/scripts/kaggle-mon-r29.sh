#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kaggle-mon-r29.sh — DEEP MONITOR for the R29 26h continue-training kernel
# =============================================================================
# Polls the kernel via the API every 60s and:
#   * logs status transitions + elapsed wall time
#   * watches for GPU switches (gpu name in resume.json per segment)
#   * watches for crashes (ERROR/FAILED → still harvests whatever checkpoint
#     Kaggle saved, then re-pushes)
#   * on every end state before 26h total: downloads output → packs the newest
#     adapter+checkpoint+resume.json into the vaca-r29-resume dataset →
#     RE-PUSHES the kernel → loop. Stops when resume.json.elapsed_h >= 26.
#
# Usage:
#   bash scripts/kaggle-mon-r29.sh            # long-running watch (detached ok)
#   bash scripts/kaggle-mon-r29.sh --once     # single status + snapshot check
# Log: data/watch-r29-kaggle.log
# Output: training/cloud/kaggle-r29-output/
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

USERNAME="$(python3 -c "import json;print(json.load(open('$HOME/.kaggle/credentials.json'))['username'])" 2>/dev/null || echo stevenawoods)"
KERNEL="$USERNAME/vaca-qlora-r29-r28-continue-26h"   # resolved slug (title-derived)
DATASET_RESUME="vaca-r29-resume"
TOTAL_H=26.0
URL="https://www.kaggle.com/code/$KERNEL"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/training/cloud/kaggle-r29-output"
LOG="$ROOT/data/watch-r29-kaggle.log"
POLL=60
MAX_LOOPS=$((60 * 44))   # 44h wall cap (26h train + restart overhead + margin)

mkdir -p "$OUT_DIR" "$(dirname "$LOG")"
say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

last_status=""
prev_gpu=""

status_of() {
  python3 -m kaggle kernels status "$KERNEL" 2>/dev/null | grep -oP 'has status "\K[^"]+' || echo "UNKNOWN"
}

push_kernel() {
  local dir; dir="$(mktemp -d)"
  cp "$ROOT/kaggle_kernel/train_r29_kaggle.ipynb" "$dir/"
  sed "s/__USERNAME__/$USERNAME/g" "$ROOT/kaggle_kernel/kernel-metadata-r29.json" > "$dir/kernel-metadata.json"
  for a in $(seq 1 6); do
    say "   📤 re-pushing kernel (attempt $a)..."
    OUT="$(timeout 300 python3 -m kaggle kernels push -p "$dir" --accelerator NvidiaTeslaT4 2>&1 || true)"
    if echo "$OUT" | grep -qi "successfully pushed"; then
      say "   ✅ kernel pushed — $KERNEL"
      rm -rf "$dir"
      return 0
    fi
    say "   ⚠️  push output: $(echo "$OUT" | tail -2)"
    sleep 120
  done
  rm -rf "$dir"
  return 1
}

upload_resume() {
  # $1 = dir with the downloaded round29-kaggle output (may be partial)
  local src="$1" pack; pack="$(mktemp -d)"
  local found_ckpt="" latest=""
  # newest trainer checkpoint if any
  for d in "$src"/checkpoint-*; do
    [ -d "$d" ] || continue
    found_ckpt=1
    n=$(basename "$d" | sed 's/checkpoint-//')
    if [ -z "$latest" ] || [ "$n" -gt "${latest##*-}" ] 2>/dev/null; then latest="$d"; fi
  done
  if [ -n "$latest" ]; then cp -r "$latest" "$pack/"; fi
  if [ -f "$src/resume.json" ]; then cp "$src/resume.json" "$pack/"; fi
  # adapter-only fallback
  if [ -f "$src/final/adapter_config.json" ]; then
    cp "$src/final/adapter_config.json" "$src/final/adapter_model.safetensors" "$pack/" 2>/dev/null || true
  elif [ -n "$latest" ]; then
    cp "$latest/adapter_config.json" "$latest/adapter_model.safetensors" "$pack/" 2>/dev/null || true
  fi
  if [ ! -f "$pack/resume.json" ]; then
    say "   ❌ no resume.json in output — cannot continue; will retry kernel as-is."
    rm -rf "$pack"
    return 1
  fi
  cat > "$pack/dataset-metadata.json" <<EOF
{
  "id": "$USERNAME/$DATASET_RESUME",
  "title": "VACA R29 resume state",
  "subtitle": "In-training adapter + resume.json (elapsed tracked to 26h)",
  "licenses": [{ "name": "other" }]
}
EOF
  say "   📦 uploading resume pack → $USERNAME/$DATASET_RESUME"
  timeout 300 python3 -m kaggle datasets version -p "$pack" -m "$(python3 -c "import json;d=json.load(open('$pack/resume.json'));print(f'elapsed_h={d.get(\"elapsed_h\")} steps={d.get(\"steps_total\")}')" 2>/dev/null || echo refresh)" 2>&1 | tail -2
  rm -rf "$pack"
  # wait for ready
  for a in $(seq 1 30); do
    if timeout 60 python3 -m kaggle datasets status "$USERNAME/$DATASET_RESUME" 2>/dev/null | grep -q ready; then
      say "   ✅ resume dataset ready"
      return 0
    fi
    sleep 30
  done
  return 1
}

harvest() {
  # $1 = status string; download output; return 0 if we should re-push
  local tmp; tmp="$(mktemp -d)"
  # Kaggle finalizes the output zip a moment AFTER the run ends — retry so a
  # crash traceback (crash.log in /kaggle/working) is never lost.
  local ok=0
  for r in 1 2 3 4 5; do
    if python3 -m kaggle kernels output "$KERNEL" -p "$tmp" >/dev/null 2>&1; then
      ok=1
      # Dated snapshot dir — NEVER clobber previous evidence (cp -rn hid v6's
      # real log behind v1's stale one and cost us the traceback).
      local snap; snap="$OUT_DIR/run-$(date '+%Y%m%d-%H%M%S')"
      mkdir -p "$snap"
      cp -r "$tmp"/. "$snap"/ 2>/dev/null || true
      rm -rf "$tmp"
      tmp="$snap"
      break
    fi
    say "   ⏳ output not ready (try $r/5) — retrying in 45s…"
    sleep 45
  done
  if [ "$ok" = "1" ]; then
    # Evidence log: decode the FULL kernel log (cell stdout/stderr), persist it
    # next to the snapshot, then print a generous tail + PHASE/Traceback hits
    # so a silent preemption/OOM kill is visible, not just inferred.
    for lf in "$tmp"/*.log; do
      [ -f "$lf" ] || continue
      sz=$(stat -c %s "$lf" 2>/dev/null || echo 0)
      say "   📜 kernel log $sz bytes → decoding full…"
      python3 - "$lf" "$tmp/decoded.log" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8", errors="ignore").read().splitlines()
out = []
for raw in lines:
    raw = raw.strip().lstrip(",")
    if not raw.startswith("{"):
        continue
    try:
        o = json.loads(raw)
        d = o.get("data", "")
        if d.strip():
            out.append(d.rstrip())
    except Exception:
        pass
open(dst, "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
PYEOF
      # persist decoded text next to the snapshot for later inspection
      [ -f "$tmp/decoded.log" ] && cp "$tmp/decoded.log" "$tmp/decoded-full.txt" 2>/dev/null || true
      say "   decoded → $tmp/decoded-full.txt ($(wc -l < "$tmp/decoded-full.txt" 2>/dev/null || echo 0) lines)"
      say "   ── last 60 decoded lines ──"
      tail -n 60 "$tmp/decoded-full.txt" 2>/dev/null | while read -r l; do say "     $l"; done
      for kw in PHASE Traceback Error error OOM OutOfMemory CUDA; do
        hits=$(grep -n "$kw" "$tmp/decoded-full.txt" 2>/dev/null | tail -n 8)
        if [ -n "$hits" ]; then
          say "   ── '$kw' hits ──"
          echo "$hits" | while IFS=: read -r ln rest; do say "     [$ln] $rest"; done
        fi
      done
      break
    done
    if [ -f "$tmp/round29-kaggle/crash.log" ]; then
      say "🧨 crash.log tail:"
      tail -25 "$tmp/round29-kaggle/crash.log" | while read -r l; do say "     $l"; done
    fi
  fi
  local out="$tmp/round29-kaggle"
  if [ -f "$out/resume.json" ]; then
    local el gp
    el="$(python3 -c "import json;print(json.load(open('$out/resume.json')).get('elapsed_h',0))" 2>/dev/null || echo 0)"
    gp="$(python3 -c "import json;print(json.load(open('$out/resume.json')).get('gpu','?'))" 2>/dev/null || echo '?')"
    if [ -n "$prev_gpu" ] && [ "$gp" != "?" ] && [ "$gp" != "$prev_gpu" ]; then
      say "   🔄 GPU SWITCH DETECTED: $prev_gpu → $gp"
    fi
    [ "$gp" != "?" ] && prev_gpu="$gp"
    say "   📊 segment state: elapsed_h=$el gpu=$gp ($(python3 -c "import json;d=json.load(open('$out/resume.json'));print(f\"steps={d.get('steps_total')} s/step={d.get('s_per_step')}\")" 2>/dev/null || true))"
    if python3 -c "exit(0 if float('$el') >= $TOTAL_H - 0.05 else 1)" 2>/dev/null; then
      say "🎉 TOTAL 26h REACHED (elapsed_h=$el) — training complete!"
      if [ -f "$out/final/adapter_config.json" ]; then
        say "   Final adapter: $out/final/"
        cp -r "$out/final" "$OUT_DIR/final" 2>/dev/null || true
      fi
      find "$OUT_DIR" -maxdepth 2 -name "*.safetensors" -o -maxdepth 2 -name "*.json" | head -20 | while read -r f; do say "   out: ${f#"$OUT_DIR/"}" ; done
      rm -rf "$tmp"
      return 2
    fi
    rm -rf "$tmp"
    # pack + re-push
    upload_resume "$out" || say "   ⚠️  resume upload failed — will re-push anyway"
    return 0
  fi
  if [ "$ok" = "1" ]; then
    # Keep the snapshot as evidence (it may hold the traceback that explains
    # the crash). $tmp IS the snapshot dir here — nothing to remove.
    say "   ⚠️  no output/resume.json harvested (status=$1) — snapshot kept: $tmp"
  else
    rm -rf "$tmp"
    say "   ⚠️  no output downloadable (status=$1) — falling back to last resume state"
  fi
  return 0
}

say "👀 R29 monitor started — kernel: $KERNEL"
say "   Live view (browser): $URL"
sleep 90   # give the new push a moment to register before first status call

i=0
START="$(date +%s)"
while [ $i -lt $MAX_LOOPS ]; do
  i=$((i + 1))
  STATUS="$(status_of)"
  ELAPSED="$(( ($(date +%s) - START) / 60 ))m"
  if [ "$STATUS" != "$last_status" ]; then
    say "poll #$i — status: ${STATUS} (was: ${last_status:-none}, monitor elapsed $ELAPSED)"
    last_status="$STATUS"
  fi

  case "$STATUS" in
    *RUNNING*|*PENDING*|*QUEUED*|*UNKNOWN*)
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
    *COMPLETE*|*SUCCESS*|*DONE*)
      say "✅ Segment COMPLETE — harvesting…"
      harvest "$STATUS"; rc=$?
      if [ "$rc" = "2" ]; then break; fi
      [ "$ONCE" = "1" ] && exit 0
      say "   → re-push for next segment"
      push_kernel || say "   ❌ push failed — will retry on next poll"
      last_status=""
      sleep "$POLL"
      ;;
    *ERROR*|*FAILED*|*CANCELED*|*CANCELLED*)
      say "⚠️ Kernel $STATUS — crash suspected. Harvesting whatever survived…"
      harvest "$STATUS"; rc=$?
      if [ "$rc" = "2" ]; then break; fi
      [ "$ONCE" = "1" ] && exit 1
      say "   → re-pushing after crash"
      push_kernel || say "   ❌ push failed — will retry on next poll"
      last_status=""
      sleep "$POLL"
      ;;
    *)
      say "   poll #$i — unknown status string '$STATUS'"
      [ "$ONCE" = "1" ] && exit 3
      sleep "$POLL"
      ;;
  esac
done

say "monitor finished (loop cap ${MAX_LOOPS}) — last status: $(status_of)"
exit 0