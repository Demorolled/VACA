#!/usr/bin/env python3
"""
R19 capture session — harvest tsc-clean training rows by running the REAL
pipeline (local dspark; no Kaggle quota involved).

  A. Blueprint builds: 8 goals mapped to ARCHITECTURALLY DIVERSE blueprints
     (T4: the R18 session's dedup-heavy goals — 3/8 builds added zero rows —
     were all CRUD/productivity apps mapping to near-identical architectures,
     so dedup collapsed them). Each tsc-clean build auto-captures 2-5 verified
     multi-file rows into training/dataset/verified-generations.jsonl.
  B. Full-stack write cycles: the audit's section-11 request repeated; a
     tsc-clean write auto-captures ~8-11 rows (core + UI + tests + Dockerfile)
     via the codePlanner _training.json sidecar gate.

Requests run in daemon threads with LONG timeouts (builds take 8-10 min and the
HTTP response is a single blob at the END — a short client timeout aborted
still-running builds and logged status=0 even though the backend captured the
rows server-side, T3a). While a request runs, the main thread heartbeats on
verified-generations.jsonl growth so the session never looks hung and the
client reports progress instead of a blind timeout.

Logs progress (unbuffered) to stdout; print a final summary with the
verified-generations.jsonl growth.
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
CAPTURE = ROOT / "training" / "dataset" / "verified-generations.jsonl"

# T4 — diversity by design: each goal maps to a DIFFERENT blueprint family so
# the captured file sets differ (module checklists, wiring, stacks) and dedup
# can't collapse them the way the R18 all-CRUD list did (budget/notes/habit
# added zero rows). todo_list stays as the R19 continuity anchor.
BUILD_GOALS = [
    "a todo list app with tasks, due dates, and projects",           # todo_list
    "a recipe manager app with ingredient lists and step-by-step instructions",  # recipe_manager
    "an inventory management app with stock levels and reorder alerts",          # inventory_manager
    "a music player app with playlists and playback controls",                   # music_player
    "a photo editing app with filters, crop, and export",                        # photo_editor
    "an email client app with folders and a message list",                       # email_client
    "a whiteboard drawing app with shapes and freehand tools",                   # paint_studio
    "a sqlite database inspector with table browsing and query runner",          # sqlite_inspector
]

METH_REQ = ("a full-stack note-taking app in TypeScript: Express API core logic, "
            "a React frontend wired to the API, unit tests, and a Dockerfile for deployment")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api(method, path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except Exception as e:
        return 0, {"error": str(e)}


def capture_lines():
    try:
        return sum(1 for _ in open(CAPTURE))
    except FileNotFoundError:
        return 0


def fire_async(path, body, timeout):
    """POST in a daemon thread; returns a dict the thread fills with
    {'st': ..., 'd': ...} when the (long, single-blob) response arrives."""
    holder = {}

    def work():
        st, d = api("POST", path, body, timeout=timeout)
        holder["st"] = st
        holder["d"] = d

    threading.Thread(target=work, daemon=True).start()
    return holder


def wait_with_heartbeat(holder, label, settle_secs=240):
    """Wait for the request thread, heartbeat-logging capture growth every 30s
    so the session shows the build is alive. A LONG stall with NO growth is
    logged honestly (the backend's own repair loops are bounded, so the build
    always resolves — but the log should say what it sees). Returns (st, d)."""
    last = capture_lines()
    last_change = time.time()
    while "st" not in holder:
        time.sleep(30)
        now = capture_lines()
        if now != last:
            log(f"  {label}: verified rows {last} → {now} (capture growing — build alive)")
            last = now
            last_change = time.time()
        elif time.time() - last_change > settle_secs:
            log(f"  {label}: no capture growth for {settle_secs}s — still waiting (compile/repair can run long before capture)")
            last_change = time.time()
    return holder["st"], holder["d"]


def run_builds():
    before = capture_lines()
    for i, goal in enumerate(BUILD_GOALS, 1):
        log(f"── build {i}/{len(BUILD_GOALS)}: {goal[:60]!r} ──")
        # Builds run 8-10+ min and respond with ONE JSON at the end (silent
        # socket meanwhile) — a 600s client timeout used to abort still-running
        # builds and log status=0. Fire it in a thread with a long timeout and
        # heartbeat on capture growth instead of staring at a blind timeout.
        holder = fire_async("/api/blueprint/build", {"goal": goal}, timeout=1500)
        st, d = wait_with_heartbeat(holder, f"build {i}")
        bp = (d or {}).get("blueprint") or {}
        ok = bool(bp) and st == 200
        after = capture_lines()
        vc = (d or {}).get("verifiedCapture") or {}
        log(f"build {i}: status={st} blueprint={ok} captured_delta={after - before}"
            f" captured={vc.get('captured')} skipped={vc.get('skipped')} reason={str(vc.get('reasons'))[:80]}")
        before = after
        if not ok:
            log(f"  detail: {str(d)[:200]}")
        time.sleep(3)


def run_writes(n=6):
    before = capture_lines()
    for i in range(1, n + 1):
        log(f"── write {i}/{n} ──")
        stp, pland = api("POST", "/api/reason/plan-code",
                         {"request": METH_REQ, "scale": "small"}, timeout=300)
        plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
        pfiles = plan.get("files") or plan.get("contractFiles") or []
        if stp != 200 or not pfiles:
            log(f"write {i}/{n}: plan failed (status={stp}) — skipping")
            continue
        answers = {}
        for qi, q in enumerate((plan.get("questions") or [])[:3]):
            key = q.get("key") if isinstance(q, dict) else f"q{qi + 1}"
            opts = q.get("options") if isinstance(q, dict) else None
            answers[key] = opts[0] if opts else "yes"
        # Same single-blob-at-the-end shape as builds: thread + heartbeat.
        holder = fire_async("/api/reason/write-code",
                            {"request": METH_REQ, "plan": plan, "answers": answers,
                             "libraryMode": "hybrid", "scale": "small"}, timeout=900)
        stw, wd = wait_with_heartbeat(holder, f"write {i}")
        success = stw == 200 and isinstance(wd, dict) and wd.get("success")
        after = capture_lines()
        files = (wd or {}).get("files") or []
        classes = (wd or {}).get("tscClasses") or {}
        classes_s = f" classes={json.dumps(classes)}" if classes else ""
        log(f"write {i}/{n}: status={stw} success={success} tscErrors={(wd or {}).get('tscErrors')}"
            f" files={len(files)} captured_delta={after - before}{classes_s}")
        before = after
        time.sleep(3)


def main():
    if "--tmux" in sys.argv:
        # T3c — long-running jobs must survive terminal disconnects. Plain
        # nohup/background launches get reaped when the launching shell dies
        # (the R19 auto-push died silently exactly this way, after the capture
        # had already finished — the corpus never got built). Re-exec inside a
        # named tmux session; logs go to /tmp/r19-capture.log.
        # Re-exec explicitly via sys.executable — argv[0] may be a non-
        # executable script path when launched as `python3 script.py --tmux`.
        args = [a for a in sys.argv if a != "--tmux"]
        cmd = " ".join([shlex.quote(sys.executable), *[shlex.quote(a) for a in args]])
        subprocess.run(["tmux", "new-session", "-d", "-s", "r19-capture",
                        f"{cmd} > /tmp/r19-capture.log 2>&1"], check=False)
        print("launched in tmux session 'r19-capture' — logs: /tmp/r19-capture.log")
        print("  tmux attach -t r19-capture   (detach: Ctrl-b d)")
        print("  tmux kill-session -t r19-capture   (stop)")
        return 0
    log(f"R19 capture session start — verified-generations at {capture_lines()} rows")
    log("── Phase A: blueprint builds (diverse blueprints — T4) ──")
    run_builds()
    log("── Phase B: full-stack writes ──")
    run_writes()
    log(f"DONE — verified-generations at {capture_lines()} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
