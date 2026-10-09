#!/usr/bin/env python3
"""Fresh end-to-end UI check at localhost:5173.

Part A: manual/render check that the React shell loads (index, root mount, bundle).
Part B: full UI flow replay through the vite proxy -- the exact API sequence
ReasoningPanel.tsx uses: plan-code -> answers -> write-code. Verifies the
"Wrote N files" success message and the rendered file list (the response the
UI renders, plus on-disk export dir being the newest).
"""
import json
import os
import glob
import re
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5173"          # vite proxy = exactly what the browser calls
ROOT = "/home/final-flash1/Desktop/visual-ai-architect"
REQUEST = "make a complete chess game with an AI player"
MIN_BYTES = 200

# A/B switch: which one-shot library strategy to test.
#   goal      = full budget to getLibraryContext(request)            (baseline)
#   hybrid    = 900 goal + 900 node-type                             (shipped default)
#   dominant  = full budget to getLibraryContextForNodeType(...)     (replacement)
LIBRARY_MODE = os.environ.get("LIBRARY_MODE") or (sys.argv[1] if len(sys.argv) > 1 else "hybrid")
if LIBRARY_MODE not in ("goal", "hybrid", "dominant"):
    print("ERROR: LIBRARY_MODE must be goal|hybrid|dominant, got", LIBRARY_MODE)
    sys.exit(2)


def fetch(path, timeout=30):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "vaca-ui-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def post(path, body, timeout=1800):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        print("  HTTP ERROR %s: %s" % (e.code, raw[:400]))
        raise


def pick_answer(q, i):
    """Accept dict or string questions; return a sensible answer string.
    Structured choice questions pick the best matching option (never 'Yes')."""
    opts = []
    text = ""
    if isinstance(q, dict):
        text = (q.get("question") or q.get("text") or "").lower()
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


print("=" * 60)
print("PART A: frontend render shell check")
print("=" * 60)
try:
    status, html = fetch("/", timeout=15)
    print("index  : HTTP %d, %d bytes" % (status, len(html)))
    print("root#id: %s" % ("PRESENT" if 'id="root"' in html else "MISSING"))
    bundles = re.findall(r'src="([^"]+\.(?:js|tsx))"', html)
    for b in bundles:
        try:
            bs, body = fetch(b, timeout=30)
            print("bundle : %s -> HTTP %d, %d bytes" % (b, bs, len(body)))
        except Exception as e:
            print("bundle : %s -> ERROR %s" % (b, e))
    if not bundles:
        print("bundle : none found in index (SPA may inline)")
except Exception as e:
    print("RENDER CHECK ERROR:", e)

print()
print("=" * 60)
print("PART B: UI flow replay (plan -> answers -> write) via :5173 proxy")
print("=" * 60)

t0 = time.time()
plan_resp = post("/api/reason/plan-code", {"request": REQUEST})
print("STEP 1 plan-code via :5173 proxy - %.1fs" % (time.time() - t0))
print("  success:", plan_resp.get("success"))
print("  message:", str(plan_resp.get("message"))[:160])
plan = plan_resp.get("plan") or {}
files = plan.get("files") or []
print("  planned files: %d" % len(files))
for f in files:
    print("    - %s  (%s)" % (f.get("path"), (f.get("summary") or "")[:60]))

questions = plan.get("questions") or plan_resp.get("questions") or []
print("  questions asked: %d" % len(questions))
if questions:
    print("  question[0] schema:", json.dumps(questions[0])[:200])

answers = {}
for i, q in enumerate(questions):
    if isinstance(q, dict):
        key = q.get("key") or q.get("id") or ("q%d" % i)
    else:
        key = "q%d" % i
    ans = pick_answer(q, i)
    answers[key] = ans
    print("  answered %s -> %s" % (key, ans))

print("STEP 2 answers:", json.dumps(answers)[:200])
print("LIBRARY_MODE:", LIBRARY_MODE, "(sent as libraryMode in write-code body)")

t0 = time.time()
write_resp = post(
    "/api/reason/write-code",
    {"request": REQUEST, "plan": plan, "answers": answers, "libraryMode": LIBRARY_MODE},
)
print("STEP 3 write-code via :5173 proxy - %.1fs" % (time.time() - t0))
print("  success:", write_resp.get("success"))
print("  MODE:", write_resp.get("mode"))
print("  libraryMode:", LIBRARY_MODE)
print("  writtenCount:", write_resp.get("writtenCount"), "totalFiles:", write_resp.get("totalFiles"))
summary = write_resp.get("summary") or ""
print("  SUMMARY (what the UI renders, ReasoningPanel L670):", str(summary)[:300])
export_dir = write_resp.get("exportDir") or ""
print("  exportDir:", export_dir)
resp_files = write_resp.get("written") or write_resp.get("files") or []
print("  response per-file list: %d entries (field %s)" % (len(resp_files), "written" if write_resp.get("written") else "files"))
for rf in resp_files:
    print("    - %s" % (rf.get("path") if isinstance(rf, dict) else rf))

print("STEP 4.5: tsc compile gate on the exported files")
compile_ok = True
import subprocess
TSC = os.path.join(ROOT, "node_modules", ".bin", "tsc")
ts_paths = [os.path.join(export_dir, f.get("path")) for f in files if str(f.get("path", "")).endswith((".ts", ".tsx"))]
if ts_paths:
    try:
        r = subprocess.run(
            [TSC, "--noEmit", "--target", "ES2020", "--module", "ESNext", "--moduleResolution", "bundler", "--skipLibCheck"] + ts_paths,
            capture_output=True, text=True, timeout=120,
        )
        errs = [ln for ln in r.stdout.splitlines() if "error TS" in ln]
        print("  tsc errors: %d" % len(errs))
        for e in errs[:8]:
            print("   ", e.strip())
        compile_ok = len(errs) == 0
    except Exception as e:
        print("  tsc FAILED to run:", e)
        compile_ok = False
else:
    print("  (no .ts files to compile)")

print("STEP 4 on-disk verification (min %d bytes/file to catch stubs)" % MIN_BYTES)
all_exist = True
for f in files:
    p = os.path.join(export_dir, f.get("path", ""))
    ok = os.path.isfile(p)
    size = os.path.getsize(p) if ok else 0
    ok = ok and size >= MIN_BYTES
    all_exist = all_exist and ok
    print("  %s %s (%d bytes)" % ("OK " if ok else "MISSING", p, size))

newest = None
if os.path.isdir(os.path.join(ROOT, "backend", "exports")):
    dirs = glob.glob(os.path.join(ROOT, "backend", "exports", "*") + "/")
    if dirs:
        newest = max(dirs, key=os.path.getmtime)
print("  newest exports dir:", newest)
is_newest = bool(newest) and newest.rstrip("/") == export_dir.rstrip("/")
print("  is newest:", is_newest)

written = int(write_resp.get("writtenCount") or 0)
total = int(write_resp.get("totalFiles") or len(files))
resp_count = len(resp_files)
verdict = (
    len(files) >= 1
    and all_exist
    and written == total == len(files)
    and resp_count >= written
    and bool(write_resp.get("success"))
    and bool(summary)
    and is_newest
    and bool(export_dir)
    and compile_ok
)
print()
if verdict:
    print("VERDICT: UI-FLOW OK - '%s' + %d-file list render + tsc-clean" % (summary, written))
else:
    print("VERDICT: FAIL - see steps above")
print("DONE")
