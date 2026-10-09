#!/usr/bin/env python3
"""Live test: drive a CHECKERS build through the live backend and watch the
playability probe + render repair loop.

A checkers board is a stronger probe test than tic-tac-toe: it starts with
pieces on the board (occupied cells), and a broken build typically renders
pieces that can be selected but never moved — the exact static-board class the
probe exists to catch.

Usage: python3 scripts/live-checkers-test.py
"""
import json
import sys
import time
import urllib.request

BASE = "http://localhost:3001"
REQ = ("Build a checkers game in a single HTML file. 8x8 board, 12 red pieces "
       "and 12 black pieces, alternating turns. Clicking your piece must show "
       "the legal moves it can make, and clicking a legal destination must "
       "move the piece. Pieces move diagonally forward and capture by jumping.")


def api(method, path, body=None, timeout=600):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    log("step 1: plan-code")
    st, d = api("POST", "/api/reason/plan-code", {"request": REQ, "scale": "small"}, timeout=300)
    plan = (d.get("plan") or {}) if isinstance(d, dict) else {}
    pfiles = plan.get("files") or plan.get("contractFiles") or []
    if st != 200 or not pfiles:
        log(f"PLAN FAILED status={st} resp={json.dumps(d)[:300]}")
        return 1
    log(f"plan ok: {len(pfiles)} file(s): {[f.get('path') for f in pfiles]}")

    answers = {}
    for q in (plan.get("questions") or [])[:4]:
        key = q.get("key") if isinstance(q, dict) else "q"
        opts = q.get("options") if isinstance(q, dict) else None
        answers[key] = opts[0] if opts else "yes"

    log("step 2: write-code (can take 5-10 min on the 14B — watching…)")
    t0 = time.time()
    stw, wd = api("POST", "/api/reason/write-code",
                  {"request": REQ, "plan": plan, "answers": answers,
                   "libraryMode": "hybrid", "scale": "small"}, timeout=1500)
    elapsed = int(time.time() - t0)
    log(f"write returned after {elapsed}s status={stw}")

    if not isinstance(wd, dict):
        log(f"response not dict: {str(wd)[:300]}")
        return 1

    for key in ("success", "tscErrors", "mode", "repairRounds", "error"):
        if key in wd:
            log(f"  {key}: {wd[key]}")

    rs = wd.get("renderSmoke")
    if isinstance(rs, dict):
        log(f"  renderSmoke.status: {rs.get('status')}")
        log(f"  renderSmoke.detail: {rs.get('detail')}")
        for e in (rs.get("errors") or [])[:6]:
            log(f"    smoke error: {str(e)[:160]}")
    else:
        log(f"  renderSmoke: {rs}")

    files = wd.get("files") or []
    log(f"  files: {len(files)}")
    html = next((f for f in files if str(f.get('path', '')).endswith('.html')), None)
    if html:
        content = html.get("content") or ""
        log(f"  index.html: {len(content)} chars, click logic present: "
            f"{'addEventListener' in content or 'onclick' in content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
