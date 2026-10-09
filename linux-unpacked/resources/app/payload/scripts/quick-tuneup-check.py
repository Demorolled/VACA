#!/usr/bin/env python3
"""quick-tuneup-check.py — recent tune-up actions from the combined corpus."""
import json, sys
from collections import Counter
path = sys.argv[1] if len(sys.argv) > 1 else "training/cloud/puzzle-r30/opt-puzzle-r30.jsonl"
rows = [json.loads(l) for l in open(path) if l.strip()]
print("total opt rows:", len(rows))
new = rows[-8:]
print("recent actions:", dict(Counter(r["action"] for r in new)))
for r in new[-4:]:
    act = r["action"]
    mark = "ok" if r.get("valid") else "BAD" if r["reward"] < 0 else "keep"
    print("  %s %-30s %-9s %s reward=%+d %s" % (
        r["ts"][11:19], r["app"][:28], act, mark, r["reward"], r["reason"]))