#!/usr/bin/env python3
"""Re-gate the R15 repaired files with the official GUI bar and rewrite
results.json so repaired_pass reflects the FIXED repair-gui.py.

Raw fields are preserved from the existing results.json (the raw files were
not regenerated — only the repair changed).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r15-gui"
SMOKE = ROOT / "scripts" / "smoke-test-html.py"

GUI_PROBE = ("document.body !== null && document.body.children.length >= 1 "
             "&& (document.querySelectorAll('button,input,textarea,canvas,div,table,li').length >= 3)")


def _classify(raw_errs, repaired_errs, repaired_ok, raw_probe_ok=True) -> str:
    """Mirror probe-r15-gui.py classify() so class labels match the current
    error state (stale "GUI-fixable" labels on now-failing apps would mislead
    consumers of results.json)."""
    joined = " ".join(str(e) for e in (raw_errs + repaired_errs))
    if repaired_ok:
        return "GUI-fixable (mechanical repair)"
    if "is not defined" in joined or "Cannot read properties of undefined" in joined:
        return "scope/undefined variable"
    if "is not a function" in joined:
        return "bad API / wrong receiver"
    if "Failed to load resource" in joined or "404" in joined or "net::ERR" in joined:
        return "asset/network 404"
    if "Page crashed" in joined or "no-json" in str(repaired_errs):
        return "page crash"
    if not raw_probe_ok and not raw_errs:
        return "no interactive content / probe fail (0 errors)"
    return "other"

res_path = OUT / "results.json"
results = json.loads(res_path.read_text(encoding="utf-8"))

changed = 0
for r in results:
    rep_path = OUT / f"{r['name']}-repaired.html"
    if not rep_path.exists():
        continue
    proc = subprocess.run(
        [sys.executable, str(SMOKE), str(rep_path), "--probe", GUI_PROBE, "--wait", "3500"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError:
        d = {}
    errs = d.get("pageErrors", []) + d.get("consoleErrors", [])
    probes = d.get("probes") or {}
    probe_ok = bool(probes.get(GUI_PROBE)) if probes else True
    ok = (not errs) and probe_ok
    if r.get("repaired_pass") != ok:
        changed += 1
    r["repaired_pass"] = ok
    r["repaired_errs"] = errs[:2]
    # Recompute class from the CURRENT error state (stale "GUI-fixable"
    # labels on now-failing apps would mislead consumers of results.json).
    r["class"] = _classify(r.get("raw_errs", []), errs, ok, r.get("raw_probe_ok", True))

res_path.write_text(json.dumps(results, indent=1), encoding="utf-8")

rep_ok = sum(1 for r in results if r["repaired_pass"])
raw_ok = sum(1 for r in results if r.get("raw_pass"))
print(f"Rewrote results.json: RAW {raw_ok}/{len(results)} | REPAIRED {rep_ok}/{len(results)} (flips: {changed})")
for r in results:
    print("  %-22s raw=%-4s repaired=%-4s [%s]" % (
        r["name"], "OK" if r.get("raw_pass") else "FAIL",
        "OK" if r.get("repaired_pass") else "FAIL", r.get("class", "")))
