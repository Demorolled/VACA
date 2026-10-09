#!/usr/bin/env python3
"""CONTROLLED A/B: library-context strategies on the SAME plan.

Unlike ui-chess-flow-check.py (which re-plans per run and therefore compares
different plans), this harness:

  1. POSTs /api/reason/plan-code ONCE -> plan + questions
  2. Builds answers for those questions (same answer set for all modes)
  3. POSTs /api/reason/write-code ONCE PER MODE with the SAME plan + answers,
     differing only in libraryMode:
       - goal      (baseline: full 1800 budget to getLibraryContext)
       - hybrid    (shipped: 900 goal + 900 node-type when dominant known)
       - dominant  (replacement: full 1800 budget to getLibraryContextForNodeType)
  4. Runs `tsc --noEmit` on each export dir and reports error counts side by side,
     gated on PLANNED-FILE COVERAGE: if a mode wrote fewer files than planned
     (a partial one-shot — the known truncation failure class), its tsc count is
     NOT comparable and is flagged invalid for the delta.

The only variable between the write calls is `libraryMode` — the request, plan,
answers, and model state are identical, so tsc-error deltas measure the context
strategy alone (when coverage is full).

Usage:
  AB_MODES=goal,hybrid python3 scripts/ab-controlled.py          # choose modes
  python3 scripts/ab-controlled.py "<request>"                   # custom request
  PORT=3001 python3 scripts/ab-controlled.py                     # direct to backend
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

PORT = os.environ.get("PORT", "5173")  # vite proxy (browser path); PORT=3001 hits backend directly
BASE = "http://127.0.0.1:%s" % PORT
ROOT = "/home/final-flash1/Desktop/visual-ai-architect"
REQUEST = sys.argv[1] if len(sys.argv) > 1 else "make a complete chess game with an AI player"
# Modes to A/B (comma-separated env override, default goal vs hybrid).
MODES = [m.strip() for m in os.environ.get("AB_MODES", "goal,hybrid").split(",") if m.strip()]
MIN_BYTES = 200
VALID_MODES = ("goal", "hybrid", "dominant")
for m in MODES:
    if m not in VALID_MODES:
        print("ERROR: AB_MODES must be a subset of %s, got %s" % (list(VALID_MODES), MODES))
        sys.exit(2)
MODES = list(dict.fromkeys(MODES))  # dedupe (AB_MODES=goal,goal would be a self-comparison)
if len(MODES) < 2:
    print("ERROR: need at least 2 distinct modes to A/B, got", MODES)
    sys.exit(2)


def post(path, body, timeout=1800):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
            return data, time.time() - t0
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        print("  HTTP ERROR %s: %s" % (e.code, raw[:400]))
        raise


def pick_answer(q):
    """Sensible answer for a structured or legacy question (never bare 'Yes')."""
    opts, text = [], ""
    if isinstance(q, dict):
        text = (q.get("question") or "").lower()
        opts = [str(o) for o in (q.get("options") or [])]
    else:
        text = str(q).lower()
    if not opts:
        return "Yes"
    if any(k in text for k in ("interface", " ui", "web", "console", "graphic", "display", "canvas")):
        for o in opts:
            lo = o.lower()
            if any(k in lo for k in ("web", "canvas", "graphic", "gui", "html")):
                return o
    if any(k in text for k in ("difficult", "ai", "depth", "engine", "minimax", "strength")):
        for o in opts:
            lo = o.lower()
            if any(k in lo for k in ("depth", "medium", "intermediate", "minimax")):
                return o
    if any(k in text for k in ("language", "typescript", "lang")):
        for o in opts:
            if "typescript" in o.lower() or o.lower().startswith("ts"):
                return o
    return opts[0]


def tsc_errors(export_dir, files):
    """Compile the exported .ts files (the planned subset) and count TS errors."""
    TSC = os.path.join(ROOT, "node_modules", ".bin", "tsc")
    ts_paths = [os.path.join(export_dir, f.get("path", "")) for f in files if str(f.get("path", "")).endswith((".ts", ".tsx"))]
    if not ts_paths:
        return 0, []
    r = subprocess.run(
        [TSC, "--noEmit", "--target", "ES2020", "--module", "ESNext", "--moduleResolution", "bundler", "--skipLibCheck"] + ts_paths,
        capture_output=True, text=True, timeout=120,
    )
    errs = [ln for ln in r.stdout.splitlines() if "error TS" in ln]
    return len(errs), errs[:10]


print("=" * 66)
print("CONTROLLED A/B — same plan+answers, only libraryMode differs")
print("request: %s" % REQUEST)
print("base   : %s" % BASE)
print("=" * 66)

# 1) Plan ONCE
t0 = time.time()
plan_resp, _ = post("/api/reason/plan-code", {"request": REQUEST})
plan = plan_resp.get("plan") or {}
files = plan.get("files") or []
questions = plan.get("questions") or []
print("STEP 1 plan-code (%.1fs): %d files, %d questions" % (time.time() - t0, len(files), len(questions)))
for f in files:
    print("    - %s (%s) exports=%s" % (f.get("path"), f.get("language"), (f.get("exports") or [])[:6]))
if not files:
    print("FATAL: no plan files"); sys.exit(2)

answers = {}
for i, q in enumerate(questions):
    key = (q.get("key") or q.get("id") or ("q%d" % i)) if isinstance(q, dict) else ("q%d" % i)
    answers[key] = pick_answer(q)
print("answers:", json.dumps(answers)[:200])

# 2) Write TWICE with the same plan, different libraryMode
results = {}
for mode in MODES:
    print("\nSTEP 2 write-code libraryMode=%s ..." % mode)
    resp, dt = post("/api/reason/write-code", {"request": REQUEST, "plan": plan, "answers": answers, "libraryMode": mode})
    export_dir = resp.get("exportDir") or ""
    written = resp.get("written") or resp.get("files") or []
    written_count = resp.get("writtenCount") or len(written)
    print("  %s: %s (%.0fs) | writeMode=%s | %d/%d written | exportDir=%s" % (
        mode, resp.get("summary"), dt, resp.get("mode"), written_count, resp.get("totalFiles"), export_dir))

    # stub check: every planned file exists with >= MIN_BYTES, and count the
    # actual files that landed on disk (partial one-shot -> coverage < planned).
    missing = []
    for f in files:
        p = os.path.join(export_dir, f.get("path", ""))
        ok = os.path.isfile(p) and os.path.getsize(p) >= MIN_BYTES
        if not ok:
            missing.append(f.get("path", "?"))
            print("  MISSING/SHORT: %s" % p)
    all_exist = len(missing) == 0
    coverage = len(files) - len(missing)

    n_err, errs = tsc_errors(export_dir, files)
    print("  tsc errors: %d%s" % (n_err, "" if all_exist else " (files missing!)"))
    for e in errs:
        print("   ", e.strip())
    results[mode] = {
        "export_dir": export_dir, "write_mode": resp.get("mode"), "written": written_count,
        "coverage": coverage, "planned": len(files), "tsc_errors": n_err,
        "files_ok": all_exist, "seconds": round(dt),
    }

# 3) Comparison
print("\n" + "=" * 66)
print("COMPARISON (same %d-file plan, same answers)" % len(files))
print("=" * 66)
for mode in MODES:
    r = results[mode]
    print("  %-9s writeMode=%-8s coverage=%d/%-2d tsc_errors=%-3d valid=%s  (%ds)" % (
        mode, r.get("write_mode", "one-shot"), r["coverage"], r["planned"],
        r["tsc_errors"], "YES" if r["files_ok"] else "NO — partial write", r["seconds"]))
# Delta is only meaningful when EVERY mode wrote all planned files.
all_full = all(r["files_ok"] for r in results.values())
a = MODES[0]
b = MODES[1]
base = results[a]["tsc_errors"]
alt = results[b]["tsc_errors"]
if all_full:
    print("  delta: %s=%d -> %s=%d (%s%d errors%s)" % (
        a, base, b, alt, "-" if alt < base else "+", abs(alt - base),
        " — %s wins" % b if alt < base else (" — %s wins" % a if base < alt else " — tie")))
else:
    print("  NO VALID tsc DELTA: at least one mode had a partial write (coverage < planned)")
    print("  -> re-run the incomplete mode(s) or use chunked generation (chunkSize=2) for coverage")
print("DONE")
