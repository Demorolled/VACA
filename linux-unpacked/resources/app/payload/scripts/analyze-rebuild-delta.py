#!/usr/bin/env python3
"""Analyze the post-rebuild scan vs the pre-rebuild baseline."""
import json, re, collections
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# Which builds were actually rebuilt through the fixed pipeline. The rebuild
# phase overwrites the manifest record with a FRESH `builtAt` on success, so the
# MANIFEST is the source of truth — NOT the run log (which is rewritten on every
# invocation, so stale/missing entries would misreport rebuilt builds as skipped).
# A build counts as regenerated when its builtAt falls on the same (latest) day
# as the rebuild run; a failed attempt (❌) leaves the old timestamp in place.
manifest = json.loads((BASE / "data/campaign50-manifest.json").read_text())
names = [b["name"] for b in manifest.get("builds", [])]
stamps = [b.get("builtAt") for b in manifest.get("builds", []) if b.get("builtAt")]
if stamps:
    latest_day = max(s[:10] for s in stamps)  # YYYY-MM-DD
    rebuilt = {b["name"] for b in manifest.get("builds", [])
               if (b.get("builtAt") or "").startswith(latest_day)}
else:
    rebuilt = set()
skipped = [n for n in names if n not in rebuilt]
print(f"Manifest builds: {len(names)} | Rebuilt (manifest builtAt): {len(rebuilt)} | Skipped: {skipped or 'none'}")

# Post-rebuild scan
scan = json.loads((BASE / "data/campaign50-scan.json").read_text())
results = scan["results"]
passed = [r for r in results if r["pass"]]
failed = [r for r in results if not r["pass"]]
print(f"\n=== POST-REBUILD: PASS {len(passed)} / {len(results)} ===")

# Categorize remaining failures
codes = collections.Counter()
stub_builds = set()
sec_builds = set()
adv_builds = set()
for r in failed:
    for p in r["problems"]:
        if p.startswith("stubs:"):
            stub_builds.add(r["name"])
        if p.startswith("security:"):
            sec_builds.add(r["name"])
        if p.startswith("advisory:"):
            adv_builds.add(r["name"])
        if "tsc:" in p:
            for c in re.findall(r"TS(\d+)", p):
                codes[int(c)] += 1

print("\n=== REMAINING ERROR CODES (post-rebuild) ===")
for code, count in sorted(codes.items()):
    print(f"  TS{code}: {count}")
print(f"  (total tsc error mentions: {sum(codes.values())})")
print(f"\n  Stub builds: {len(stub_builds)} -> {sorted(stub_builds)}")
print(f"  Security builds: {len(sec_builds)} -> {sorted(sec_builds)}")
print(f"  Advisory builds: {len(adv_builds)}")

print("\n=== FAILED BUILDS (first problem each) ===")
for r in failed:
    print(f"  ❌ {r['name']:35s} [{r['tier']:7s}]  {r['problems'][0][:110]}")

print("\n=== INDEX.TS SPECIFIC ERRORS (systematic, should be 0) ===")
idx = [p for r in failed for p in r["problems"] if "tsc:" in p and "index.ts" in p]
if idx:
    for p in idx[:10]:
        print(f"  - {p[:120]}")
else:
    print("  NONE — all index.ts entry points compile clean ✅")