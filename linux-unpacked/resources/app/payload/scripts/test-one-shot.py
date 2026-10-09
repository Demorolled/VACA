#!/usr/bin/env python3
"""Live probe of the one-shot code generation design (codePlanner /write-code).
Calls plan-code then write-code WITHOUT chunkSize so the one-shot path runs,
and reports timing, mode, tsc/contract health, and file quality signals.
"""
import json, sys, time, urllib.request, urllib.error, os, re, subprocess

BASE = "http://127.0.0.1:3001"

def api(method, path, body=None, timeout=900):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return time.time() - t0, r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return time.time() - t0, e.code, {"error": e.read().decode()[:300]}
    except Exception as e:
        return time.time() - t0, -1, {"error": str(e)[:300]}

request = sys.argv[1] if len(sys.argv) > 1 else "a small todo list CLI app with add, list, complete commands"

print("=" * 72)
print("ONE-SHOT DESIGN PROBE")
print(f"request: {request}")
print("=" * 72)

# ── 1. Plan ──
print("\n[1] plan-code ...")
dt, st, plan = api("POST", "/api/reason/plan-code",
                   {"request": request, "scale": "small"}, timeout=300)
print(f"    plan: {st} in {dt:.1f}s")
if st != 200 or not plan.get("success"):
    print("    PLAN FAILED:", json.dumps(plan)[:300]); sys.exit(1)
files = plan.get("plan", {}).get("files", []) or plan.get("plan", {}).get("contractFiles", [])
questions = plan.get("plan", {}).get("questions", [])
print(f"    planned files: {len(files)} | questions: {len(questions)}")
for f in files[:10]:
    print(f"      - {f.get('path')} ({f.get('language')}) exports={f.get('exports')} uses={len(f.get('uses') or [])}")
answers = {}
for q in (questions or [])[:3]:
    if q.get("options"):
        answers[q["key"]] = q["options"][0]
    else:
        answers[q["key"]] = "yes"

# ── 2. Write (one-shot: no chunkSize) ──
print("\n[2] write-code (ONE-SHOT — no chunkSize) ...")
dt, st, gen = api("POST", "/api/reason/write-code",
                  {"request": request, "plan": plan.get("plan"), "answers": answers,
                   "libraryMode": "hybrid", "scale": "small"},
                  timeout=900)
print(f"    write: {st} in {dt:.1f}s")
if st != 200:
    print("    WRITE FAILED:", json.dumps(gen)[:400]); sys.exit(1)
if not gen.get("success"):
    print("    GENERATION FAILED:", json.dumps(gen)[:400]); sys.exit(1)
mode = gen.get("mode")
tsc = gen.get("tscErrors", 0)
contract = gen.get("contractViolations", 0)
repair = gen.get("repairRounds", 0)
# The write-code route returns both `files` (array of {path,content}) and
# `written` (array of {path,content,status}). Read both for compatibility.
written = gen.get("written") or []
files_out = gen.get("files") or [
    {"path": w.get("path"), "content": w.get("content", "")} for w in written if isinstance(w, dict)
]
nfiles = gen.get("totalFiles") or len(written)
exportDir = gen.get("exportDir", "")
print(f"    mode={mode} | files={nfiles} | repairRounds={repair} | tscErrors={tsc} | contractViolations={contract}")
print(f"    exportDir: {exportDir}")
rs = gen.get("renderSmoke")
if rs:
    print(f"    renderSmoke: {rs.get('status')} — {rs.get('detail')}")
    for e in (rs.get("errors") or [])[:5]:
        print(f"      • {e[:140]}")

# ── 3. Real tsc check on the written output ──
print("\n[3] independent tsc check on written output ...")
if exportDir and os.path.isdir(exportDir):
    ts_files = [os.path.join(exportDir, f["path"]) for f in files_out
                if f["path"].endswith(".ts") and os.path.exists(os.path.join(exportDir, f["path"]))]
    if ts_files:
        r = subprocess.run(["npx", "tsc", "--noEmit", "--target", "ES2020", "--module", "ESNext",
                            "--moduleResolution", "bundler", "--skipLibCheck", *ts_files],
                           capture_output=True, text=True, timeout=120)
        err_lines = [l for l in r.stdout.split("\n") if "error TS" in l and "TS5112" not in l]
        print(f"    independent tsc: {len(err_lines)} errors across {len(ts_files)} ts files")
        for l in err_lines[:8]:
            print(f"      {l.strip()[:140]}")
    else:
        print("    no .ts files to compile")
    # file size / emptiness + missing-import scan
    empties = [f["path"] for f in files_out
               if not (f.get("content") or "").strip()]
    stubs = [f["path"] for f in files_out
             if re.search(r"\b(TODO|FIXME|placeholder|not implemented|pass\s*$)", f.get("content") or "", re.I)]
    print(f"    empty files: {len(empties)} | stub/TODO files: {len(stubs)}")

# ── 4. Weakness signals ──
print("\n[4] weakness signals:")
print(f"    - one-shot mode used: {mode == 'one-shot'}")
print(f"    - any tsc errors survived: {tsc > 0}")
print(f"    - any contract violations survived: {contract > 0}")
print(f"    - repair rounds consumed: {repair}")
print(f"    - total wall time: {dt:.1f}s (user waits this long for one request)")
with open("data/one-shot-probe.json", "w") as f:
    json.dump({"request": request, "dt": dt, "mode": mode, "files": nfiles,
               "tscErrors": tsc, "contractViolations": contract, "repairRounds": repair,
               "exportDir": exportDir, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=1)
print("saved: data/one-shot-probe.json")
