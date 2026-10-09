#!/usr/bin/env python3
"""Analyze post-fix campaign scan results: categorize remaining failures."""
import json, re, collections
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
scan = json.loads((BASE / "data/campaign50-scan.json").read_text())
results = scan["results"]

passed = [r for r in results if r["pass"]]
failed = [r for r in results if not r["pass"]]

print(f"TOTAL: {len(results)}  PASS: {len(passed)}  FAIL: {len(failed)}")
print()

# Categorize failures
idx_ts2614 = 0
idx_ts2300 = 0
idx_ts2304 = 0
node_ts1005 = 0   # JSX-like syntax
node_ts1110 = 0   # Type expected (JSX)
node_ts1161 = 0   # Unterminated regex (JSX)
node_ts1434 = 0   # Unexpected keyword
node_ts1435 = 0   # Unknown keyword (prose leak)
node_ts1127 = 0   # Invalid character
node_ts1128 = 0   # Declaration expected
node_ts1443 = 0   # Module declaration name
node_ts2307 = 0   # Cannot find module
node_ts2305 = 0   # Module has no exported member
node_ts2614 = 0   # No exported member (default)
other_ts = 0
stub_builds = 0
sec_builds = 0
adv_builds = 0

for r in failed:
    for p in r["problems"]:
        if "stubs:" in p:
            stub_builds += 1
        if p.startswith("security:"):
            sec_builds += 1
        if p.startswith("advisory:"):
            adv_builds += 1
        if "tsc:" in p:
            # Extract error codes
            codes = re.findall(r"TS(\d+)", p)
            for c in codes:
                ci = int(c)
                if ci == 1005:
                    node_ts1005 += 1
                elif ci == 1110:
                    node_ts1110 += 1
                elif ci == 1161:
                    node_ts1161 += 1
                elif ci == 1434:
                    node_ts1434 += 1
                elif ci == 1435:
                    node_ts1435 += 1
                elif ci == 1127:
                    node_ts1127 += 1
                elif ci == 1128:
                    node_ts1128 += 1
                elif ci == 1443:
                    node_ts1443 += 1
                elif ci in (2307, 2305):
                    node_ts2307 += 1
                elif ci == 2300:
                    if "index.ts" in p:
                        idx_ts2300 += 1
                    else:
                        other_ts += 1
                elif ci == 2304:
                    if "index.ts" in p:
                        idx_ts2304 += 1
                    else:
                        other_ts += 1
                elif ci == 2614:
                    if "index.ts" in p:
                        idx_ts2614 += 1
                    else:
                        other_ts += 1
                else:
                    other_ts += 1

print("=== INDEX.TS ERRORS (systematic — should be 0) ===")
print(f"  TS2614 (no exported member / default): {idx_ts2614}")
print(f"  TS2300 (duplicate identifier):         {idx_ts2300}")
print(f"  TS2304 (cannot find name):             {idx_ts2304}")

print()
print("=== NODE SOURCE FILE ERRORS (genuine AI output issues) ===")
print(f"  TS1005 (JSX-like syntax errors):        {node_ts1005}")
print(f"  TS1110 (Type expected — JSX):           {node_ts1110}")
print(f"  TS1161 (Unterminated regex — JSX):      {node_ts1161}")
print(f"  TS1434 (Unexpected keyword — prose):    {node_ts1434}")
print(f"  TS1435 (Unknown keyword — prose):       {node_ts1435}")
print(f"  TS1127 (Invalid character):             {node_ts1127}")
print(f"  TS1128 (Declaration expected):          {node_ts1128}")
print(f"  TS1443 (Module declaration name):       {node_ts1443}")
print(f"  TS2307 (Cannot find module):            {node_ts2307}")
print(f"  Other TS errors:                        {other_ts}")

print()
print("=== OTHER FAILURES ===")
print(f"  Builds with stubs:        {stub_builds}")
print(f"  Builds with security:     {sec_builds}")
print(f"  Builds with advisory:     {adv_builds}")

print()
print("=== FAILED BUILD NAMES ===")
for r in failed:
    ps = "; ".join(r["problems"][:3])
    print(f"  ❌ {r['name']:35s} [{r['tier']:7s}]  {ps[:120]}")