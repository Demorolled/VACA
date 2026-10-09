#!/usr/bin/env python3
"""
probe-write-convergence.py — measure the write convergence rate on the current
deployed model (the NEXT_SESSION.md TODO). Runs 6 plan-code → write-code cycles
of the R19 baseline request and logs tscErrors + the tscClasses={...} telemetry
per write (#61), so the class mix can be compared against the R19 baseline:

    R19 baseline: 6 writes → tscErrors 8/1/2/0/2/0 (2/6 clean)
    Expected shift after #61: TS2304/TS2451 mostly gone, TS2339 reduced.

Each write also exercises the #63 pattern-capture wiring (tsc-clean writes store
patterns into the knowledge bank), so the run doubles as a live check that the
bank keeps growing. Requests run in daemon threads with long timeouts + a
heartbeat on log activity, so the client never reports a blind timeout on a
still-running write.

Usage:
  python3 scripts/probe-write-convergence.py         # foreground
  python3 scripts/probe-write-convergence.py --tmux  # re-exec in tmux session
                                                     # 'write-probe', log to /tmp/write-probe.log
"""
import json
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3001"
ROOT = Path(__file__).resolve().parent.parent
LOG = "/tmp/write-probe.log"

# The R19 baseline request — same request the R19 capture session's 6 writes used.
METH_REQ = ("a full-stack note-taking app in TypeScript: Express API core logic, "
            "a React frontend wired to the API, unit tests, and a Dockerfile for deployment")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def api(method, path, body, timeout=300):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:
        return 0, {"error": str(e)}


def fire_async(path, body, timeout):
    holder = {}

    def work():
        st, d = api("POST", path, body, timeout=timeout)
        holder["st"] = st
        holder["d"] = d

    threading.Thread(target=work, daemon=True).start()
    return holder


def wait_with_heartbeat(holder, label, settle_secs=300):
    """Wait for the write thread, logging a heartbeat every 30s so a long
    compile/repair never looks hung. Returns (st, d)."""
    while "st" not in holder:
        time.sleep(30)
        if time.time() - (holder.get("hb") or 0) > settle_secs:
            log(f"  {label}: still running (write can take 5-10+ min on the 14B)…")
            holder["hb"] = time.time()
    return holder["st"], holder["d"]


def run_writes(n=6):
    results = []
    for i in range(1, n + 1):
        log(f"── write {i}/{n} ──")
        stp, pland = api("POST", "/api/reason/plan-code",
                         {"request": METH_REQ, "scale": "small"}, timeout=300)
        plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
        pfiles = plan.get("files") or plan.get("contractFiles") or []
        if stp != 200 or not pfiles:
            log(f"write {i}/{n}: plan failed (status={stp}) — skipping")
            results.append({"plan_failed": stp})
            continue
        answers = {}
        for qi, q in enumerate((plan.get("questions") or [])[:3]):
            key = q.get("key") if isinstance(q, dict) else f"q{qi + 1}"
            opts = q.get("options") if isinstance(q, dict) else None
            answers[key] = opts[0] if opts else "yes"
        holder = fire_async("/api/reason/write-code",
                            {"request": METH_REQ, "plan": plan, "answers": answers,
                             "libraryMode": "hybrid", "scale": "small"}, timeout=1200)
        stw, wd = wait_with_heartbeat(holder, f"write {i}")
        success = stw == 200 and isinstance(wd, dict) and wd.get("success")
        classes = (wd or {}).get("tscClasses") or {}
        errs = (wd or {}).get("tscErrors")
        files = len((wd or {}).get("files") or [])
        classes_s = f" classes={json.dumps(classes)}" if classes else ""
        log(f"write {i}/{n}: status={stw} success={success} tscErrors={errs}"
            f" files={files} mode={(wd or {}).get('mode')}{classes_s}")
        results.append({"i": i, "status": stw, "success": success, "tscErrors": errs,
                        "classes": classes})
        time.sleep(3)
    clean = sum(1 for r in results if r.get("success") and r.get("tscErrors") == 0)
    errs = [r.get("tscErrors") for r in results if "tscErrors" in r]
    log(f"DONE — {n} writes: {clean}/{n} clean | tscErrors per write: {errs}")
    log(f"R19 baseline: 2/6 clean, tscErrors 8/1/2/0/2/0")
    return 0


def main():
    if "--tmux" in sys.argv:
        args = [a for a in sys.argv if a != "--tmux"]
        cmd = " ".join([shlex.quote(sys.executable), *[shlex.quote(a) for a in args]])
        subprocess.run(["tmux", "new-session", "-d", "-s", "write-probe",
                        f"{cmd} > {LOG} 2>&1"], check=False)
        print("launched in tmux session 'write-probe' — logs: /tmp/write-probe.log")
        print("  tmux attach -t write-probe   (detach: Ctrl-b d)")
        print("  tmux kill-session -t write-probe   (stop)")
        return 0
    log(f"write-convergence probe start (model: see /api/health)")
    run_writes(6)
    return 0


if __name__ == "__main__":
    sys.exit(main())
