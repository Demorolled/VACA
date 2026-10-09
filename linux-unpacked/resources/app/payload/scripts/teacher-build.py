#!/usr/bin/env python3
"""
Teacher Build Driver
====================
The TEACHER side of the Buffy↔VACA loop: take ONE shaped goal/purpose and drive
it through VACA's REAL builder pipeline (/api/blueprint/build), capture the
full verdict (blueprint match, per-file tsc errors, drift, research/knowledge
injection, timing, dspark tokens), and append a session record to
data/teacher/sessions.jsonl (plus dump the raw response to
data/teacher/sessions/<seq>.json).

Usage:
  python3 scripts/teacher-build.py "GOAL" [--purpose "PURPOSE"]
                                        [--os linux|windows|mac] [--scale small|medium|large]
                                        [--no-smoke] [--sessions data/teacher/sessions.jsonl]
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
API = "http://localhost:3001"
DSPARK = "http://localhost:8000"
SESSIONS_DEFAULT = ROOT / "data" / "teacher" / "sessions.jsonl"
SESSION_DIR = ROOT / "data" / "teacher" / "sessions"
LOCK_FILE = ROOT / "data" / "teacher" / ".build.lock"
# The 14B dspark serves ~5-11 tok/s, so a small build (5 modules + repair
# rounds + smoke) can take 30-45 min. 1800s was too short: the client died
# at the timeout while the server kept churning, leaving orphaned pending
# projects. 5400s (90 min) covers even a slow medium build.
DEFAULT_BUILD_TIMEOUT = 5400


def post(url: str, body: dict, timeout: int = DEFAULT_BUILD_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def acquire_lock() -> Path | None:
    """Take an exclusive build lock so two teacher-build runs never serialize
    on the single dspark server (the seq-14 failure: 3 concurrent launches
    each POSTed a full build, tripled wall-clock, and all clients timed out).
    Returns the lock path on success, None if another build holds it."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Stale-lock check: a lock older than 4h is from a dead process.
        try:
            age = time.time() - LOCK_FILE.stat().st_mtime
        except FileNotFoundError:
            age = 0
        if age < 4 * 3600:
            print("  ERROR: another teacher-build is already running"
                  f" (lock: {LOCK_FILE}, age {age/60:.0f} min).")
            print("         Remove the lock file only if that process is dead.")
            return None
        os.remove(LOCK_FILE)
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}))
    return LOCK_FILE


def release_lock(lock: Path | None):
    if lock:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def post_with_heartbeat(url: str, body: dict, timeout: int = DEFAULT_BUILD_TIMEOUT, interval: int = 120):
    """POST while printing a heartbeat so a long build is visibly alive
    (the seq-14 client died silently: Python's block-buffered stdout hid
    everything when redirected, so there was no trace of what happened)."""
    result = {}
    error = {}
    done = threading.Event()

    def worker():
        try:
            result["data"] = post(url, body, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — surface any failure to the main thread
            error["exc"] = e
        finally:
            done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    start = time.time()
    while not done.wait(interval):
        print(f"  …build in progress {time.time() - start:.0f}s (~{(time.time() - start) / 60:.0f} min)"
              f" — {api_build_status()}", flush=True)
    if error.get("exc"):
        raise error["exc"]
    return result.get("data")


def api_build_status() -> str:
    """Best-effort progress line: how many projects exist with pending nodes
    right now. Keeps the heartbeat informative without polling dspark."""
    try:
        d = get(f"{API}/api/projects", timeout=5)
        if not isinstance(d, list):
            return "(no project list)"
        pending = sum(1 for p in d if any((n.get("data") or {}).get("status") == "pending"
                                          for n in (p.get("nodes") or [])))
        return f"{len(d)} projects, {pending} pending"
    except Exception:
        return "(status unavailable)"


def get(url: str, timeout: int = 15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def dspark_stats() -> dict:
    try:
        d = get(f"{DSPARK}/v1/health", timeout=8)
        return {
            "tokens": (d.get("stats") or {}).get("total_completion_tokens", 0),
            "requests": (d.get("stats") or {}).get("requests", 0),
        }
    except Exception:
        return {"tokens": None, "requests": None}


def run_smoke(files):
    """POST /api/generate/runtime-smoke with the generated files; returns verdict."""
    if not files:
        return {"status": "skipped", "detail": "no files"}
    html = next((f for f in files if (f.get("fileName") or f.get("path") or "").endswith(".html")), None)
    if not html:
        return {"status": "skipped", "detail": "no HTML entry"}
    try:
        body = {"files": [{"fileName": f.get("fileName") or f.get("path"),
                           "code": f.get("code") or f.get("content") or ""} for f in files]}
        d = post(f"{API}/api/generate/runtime-smoke", body, timeout=180)
        smoke = d.get("smoke") or {}
        return {
            "status": "pass" if smoke.get("success") else "fail",
            "available": smoke.get("available"),
            "passCount": sum(1 for c in smoke.get("checks", []) if c.get("status") == "pass"),
            "totalChecks": len(smoke.get("checks", [])),
            "consoleErrors": len(smoke.get("consoleErrors", []) or []),
            "durationMs": smoke.get("durationMs"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def next_seq(sessions_path: Path) -> int:
    if not sessions_path.exists():
        return 1
    seq = 0
    for line in sessions_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            seq = max(seq, int(json.loads(line).get("seq", 0)))
        except Exception:
            pass
    return seq + 1


def main():
    ap = argparse.ArgumentParser(description="Teacher build driver")
    ap.add_argument("goal", help="the shaped build goal (blueprint-matchable noun phrase)")
    ap.add_argument("--purpose", default="", help="feature detail / purpose passed to the builder")
    ap.add_argument("--os", default="linux", choices=["linux", "windows", "mac"])
    ap.add_argument("--scale", default="medium", choices=["small", "medium", "large"])
    ap.add_argument("--no-smoke", action="store_true", help="skip the post-build runtime smoke")
    ap.add_argument("--sessions", default=str(SESSIONS_DEFAULT))
    args = ap.parse_args()

    goal = args.goal.strip()
    sessions_path = Path(args.sessions)
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    seq = next_seq(sessions_path)

    print(f"\n{'='*70}")
    print(f"[teacher seq {seq}] GOAL: {goal}")
    if args.purpose:
        print(f"  purpose: {args.purpose[:120]}")
    print(f"  targetOS={args.os} scale={args.scale}")

    start = time.time()
    before = dspark_stats()

    lock = acquire_lock()
    if lock is None:
        return 1
    try:
        resp = post_with_heartbeat(f"{API}/api/blueprint/build",
                                   {"goal": goal, "purpose": args.purpose or None,
                                    "targetOS": args.os, "scale": args.scale})
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:800]
        print(f"  ERROR: HTTP {e.code}: {detail}")
        release_lock(lock)
        return 1
    except Exception as e:
        print(f"  ERROR: {e}")
        release_lock(lock)
        return 1
    finally:
        # Ensure the lock always clears when the build finishes (success OR
        # failure) — a stuck lock would block every future build.
        release_lock(lock)

    after = dspark_stats()
    elapsed = time.time() - start

    # Dump the raw response for deep-dive analysis.
    try:
        (SESSION_DIR / f"{seq}.json").write_text(json.dumps(resp, indent=1))
    except Exception:
        pass

    files = resp.get("files") or []
    summary = resp.get("summary") or {}
    capture = resp.get("verifiedCapture") or {}
    drift = resp.get("drift") or {}
    internal = resp.get("internalKnowledge") or {}
    research = resp.get("research") or {}
    timing = resp.get("timingMs") or {}

    file_errors = {}
    for f in files:
        raw = f.get("errors") or []
        errs = [(e.get("message") if isinstance(e, dict) else str(e)) for e in raw][:3]
        if errs:
            file_errors[f.get("fileName") or f.get("path")] = errs

    smoke = None if args.no_smoke else run_smoke(files)

    validated_count = summary.get("validated") if summary.get("validated") is not None else resp.get("validatedCount")
    if validated_count is None and files:
        validated_count = len([f for f in files if not f.get("errors")])
    total_files = summary.get("totalFiles") or len(files)
    ts_clean = resp.get("tsCompileClean") if resp.get("tsCompileClean") is not None else summary.get("tsCompileClean")
    drift_clean = drift.get("clean") if isinstance(drift, dict) else None

    grade = "PASS" if (validated_count == total_files and total_files and ts_clean and drift_clean is not False) else "FAIL"

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "seq": seq,
        "userRequest": goal,           # teacher receives the shaped goal
        "goal": goal,
        "purpose": args.purpose or None,
        "matchedBlueprint": (resp.get("blueprint") or {}).get("app_type"),
        "matchScore": resp.get("matchScore"),
        "matchedBy": resp.get("matchedBy"),
        "grade": grade,
        "rootCause": None,             # filled by the teacher after diagnosis
        "pipelineFix": None,           # filled by the teacher after fixing
        "tsCompileClean": ts_clean,
        "totalErrors": summary.get("totalErrors") if summary.get("totalErrors") is not None else resp.get("totalErrors"),
        "validatedCount": validated_count,
        "totalFiles": total_files,
        "isAllValidated": summary.get("isAllValidated") if summary.get("isAllValidated") is not None else (validated_count == total_files if total_files else resp.get("success")),
        "driftClean": drift_clean,
        "driftMissing": drift.get("missing") if isinstance(drift, dict) else None,
        "driftUnexpected": drift.get("unexpected") if isinstance(drift, dict) else None,
        "researchInjected": bool(research.get("searched")),
        "internalKnowledgeInjected": bool(internal.get("searched")),
        "verifiedCapture": {
            "captured": capture.get("captured"),
            "skipped": capture.get("skipped"),
            "reasons": capture.get("reasons"),
        },
        "durationMs": timing.get("total", int(elapsed * 1000)),
        "totalChars": summary.get("totalChars") or resp.get("totalChars"),
        "dsparkTokensDelta": (after["tokens"] - before["tokens"]) if before["tokens"] is not None and after["tokens"] is not None else None,
        "dsparkRequestsDelta": (after["requests"] - before["requests"]) if before["requests"] is not None and after["requests"] is not None else None,
        "runtimeSmoke": smoke,
        "success": resp.get("success"),
        "error": resp.get("error"),
        "fileErrors": file_errors or None,
        "notes": "",
    }

    with open(sessions_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"  → matched: {record['matchedBlueprint']} ({record['matchScore']}) [{record['matchedBy']}]")
    print(f"  → grade: {grade} | tscClean={ts_clean} errors={record['totalErrors']} "
          f"validated={validated_count}/{total_files} driftClean={drift_clean}")
    print(f"  → research={record['researchInjected']} internalKnowledge={record['internalKnowledgeInjected']} "
          f"captured={record['verifiedCapture'].get('captured')}")
    if smoke:
        print(f"  → runtime-smoke: {smoke.get('status')} ({smoke.get('passCount')}/{smoke.get('totalChecks')} checks, "
              f"{smoke.get('consoleErrors')} console errors)")
    print(f"  → duration: {record['durationMs']/1000:.1f}s | dspark tokens: {record['dsparkTokensDelta']}")
    print(f"  → session appended: {sessions_path} (seq {seq})")

    return 0 if grade == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
