#!/usr/bin/env bash
# curriculum-resume-chain.sh — unattended continuation of the curriculum pipeline.
#
# Waits for any in-flight `tests` stage to finish, then runs:
#   validate → eval → dataset
# each via run-stage.sh (resumable, 480s passes, exits when rows stop growing).
#
# The eval stage needs the student server on :8000 (the VACA backend keeps it
# alive via DSPARK_AUTOSTART). If eval produces 0 rows, we wait and retry a few
# times rather than silently passing an empty eval to the dataset builder.
#
# Usage: setsid bash scripts/curriculum-resume-chain.sh &   (fully detached)
# Log:   /tmp/curriculum-resume-chain.log
set -u
cd "$(dirname "$0")/.." || exit 1

log=/tmp/curriculum-resume-chain.log
exec >> "$log" 2>&1
echo "=== chain start $(date) ==="

# 1. Wait for the tests stage (launched earlier this session) to finish.
while pgrep -f 'bash curriculum/run-stage.sh tests' > /dev/null 2>&1; do
  sleep 30
done
echo "=== tests stage finished; starting validate $(date) ==="

# 2. validate
bash curriculum/run-stage.sh validate
echo "=== validate done ($(wc -l < curriculum/out/tests-validated.jsonl 2>/dev/null || echo 0) validated rows) $(date) ==="

# 3. eval — retry if the student server wasn't reachable and nothing was written.
for attempt in 1 2 3; do
  n=$(wc -l < curriculum/out/eval.jsonl 2>/dev/null || echo 0)
  if [ "$n" -gt 0 ]; then break; fi
  echo "=== eval attempt $attempt (student health: $(curl -s -m 5 http://127.0.0.1:8000/v1/health >/dev/null 2>&1 && echo up || echo down)) ==="
  bash curriculum/run-stage.sh eval
  n=$(wc -l < curriculum/out/eval.jsonl 2>/dev/null || echo 0)
  if [ "$n" -gt 0 ]; then break; fi
  echo "=== eval produced 0 rows on attempt $attempt; waiting 120s ==="
  sleep 120
done
echo "=== eval done ($(wc -l < curriculum/out/eval.jsonl 2>/dev/null || echo 0) rows) $(date) ==="

# 4. dataset
bash curriculum/run-stage.sh dataset
echo "=== chain complete $(date) ==="
echo "=== next: bash curriculum/curriculum.py train-script to emit the QLoRA launcher ==="
