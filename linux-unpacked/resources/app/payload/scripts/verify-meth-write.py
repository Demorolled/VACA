import json, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"
METH_REQ = ("a full-stack note-taking app in TypeScript: Express API core logic, "
            "a React frontend wired to the API, unit tests, and a Dockerfile for deployment")


def api(method, path, body, timeout):
    url = BASE + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


t0 = time.time()
try:
    stp, pland = api("POST", "/api/reason/plan-code",
                     {"request": METH_REQ, "scale": "small"}, 300)
    plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
    pfiles = plan.get("files") or plan.get("contractFiles") or []
    print(f"plan: HTTP {stp}, files={len(pfiles)}", flush=True)
    answers = {}
    for i, q in enumerate((plan.get("questions") or [])[:3]):
        key = q.get("key") if isinstance(q, dict) else f"q{i + 1}"
        opts = q.get("options") if isinstance(q, dict) else None
        answers[key] = opts[0] if opts else "yes"
    stw, wd = api("POST", "/api/reason/write-code",
                  {"request": METH_REQ, "plan": plan, "answers": answers,
                   "libraryMode": "hybrid", "scale": "small"}, 660)
    files = (wd.get("files") or []) if isinstance(wd, dict) else []
    paths = [f.get("path") for f in files if isinstance(f, dict)]
    print(f"write: HTTP {stw}, success={wd.get('success')}, files={len(files)}, "
          f"tscErrors={wd.get('tscErrors')}, mode={wd.get('mode')}, "
          f"elapsed={time.time() - t0:.0f}s", flush=True)
    print("PATHS:", json.dumps(paths), flush=True)
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:300]}", flush=True)
except Exception as e:
    print(f"ERROR after {time.time() - t0:.0f}s: {type(e).__name__}: {e}", flush=True)
