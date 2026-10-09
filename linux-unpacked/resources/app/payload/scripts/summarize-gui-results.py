#!/usr/bin/env python3
"""Summarize a GUI/3D probe results.json: totals + per-app + residual errors."""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "probes/r15-gui/results.json"
rows = json.load(open(path, encoding="utf-8"))
raw_ok = sum(1 for r in rows if r.get("raw_pass"))
rep_ok = sum(1 for r in rows if r.get("repaired_pass"))
print(f"TOTAL: {len(rows)} apps | RAW {raw_ok}/{len(rows)} | REPAIRED {rep_ok}/{len(rows)}")
for r in rows:
    print("  %-22s raw=%-4s repaired=%-4s [%s]" % (
        r["name"],
        "OK" if r.get("raw_pass") else "FAIL",
        "OK" if r.get("repaired_pass") else "FAIL",
        r.get("class", ""),
    ))
fails = [r for r in rows if not r.get("repaired_pass")]
if fails:
    print("\n=== residual failures ===")
    for r in fails:
        print("  %s:" % r["name"])
        print("    raw errs     :", r.get("raw_errs", [])[:3])
        print("    repaired errs:", r.get("repaired_errs", [])[:3])
