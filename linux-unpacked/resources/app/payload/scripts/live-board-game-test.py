#!/usr/bin/env python3
"""Live test: drive a board-game build (tic-tac-toe) through the live backend
and report what the playability probe + repair loop did.

The point: the smoke gate (with the new playability probe) must inspect the
generated HTML and either pass it, or fail it and let the render repair loop
fix the board so it's actually playable.

Usage: python3 scripts/live-board-game-test.py
"""
import json
import sys
import time
import urllib.request

BASE = "http://localhost:3001"
REQ = ("Build a tic-tac-toe game in a single HTML file. Click a square to place "
       "X, then O, alternate turns, detect win and draw. The board must be "
       "fully playable: clicking empty squares places marks and the game "
       "state visibly changes.")


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

    for key in ("success", "tscErrors", "mode", "repairRounds", "summary", "error"):
        if key in wd:
            log(f"  {key}: {wd[key]}")

    rs = wd.get("renderSmoke")
    if isinstance(rs, dict):
        log(f"  renderSmoke.status: {rs.get('status')}")
        log(f"  renderSmoke.detail: {rs.get('detail')}")
        errs = rs.get("errors") or []
        for e in errs[:6]:
            log(f"    smoke error: {str(e)[:160]}")
    else:
        log(f"  renderSmoke: {rs}")

    files = wd.get("files") or []
    log(f"  files: {len(files)}")
    html = next((f for f in files if str(f.get('path', '')).endswith('.html')), None)
    if html:
        content = html.get("content") or ""
        log(f"  index.html: {len(content)} chars, has click handler: "
            f"{'addEventListener' in content or 'onclick' in content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
