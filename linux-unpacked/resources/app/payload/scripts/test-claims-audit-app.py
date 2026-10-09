#!/usr/bin/env python3
"""Headless-Chrome smoke test for projects/claims-audit.html.
Loads the page, clicks "Run Quick Test", polls until the score ring settles,
then dumps: final score, pass/fail chips per claim, improvement card titles,
and any console errors. Uses --headless=new + --dump-dom snapshots via CDP-free
approach: launch chrome with --remote-debugging-port and drive it with the
websocket-client module (same pattern as the existing scripts/cdp-*.py)."""
import json, sys, time, urllib.request, os, subprocess

def log(*a):
    print(*a, flush=True)

CHROME = "/usr/bin/google-chrome"
PORT = 9333
URL = "http://127.0.0.1:3001/projects/claims-audit.html"

# 1. Launch headless chrome with remote debugging
proc = subprocess.Popen([
    CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
    f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
    "--user-data-dir=/tmp/vaca-audit-chrome",
    URL,
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_json(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10) as r:
        return json.loads(r.read().decode())

# 2. Wait for devtools endpoint
for _ in range(60):
    try:
        tabs = get_json("/json/list")
        if tabs:
            break
    except Exception:
        time.sleep(0.5)
else:
    log("FAIL: chrome devtools never came up"); proc.kill(); sys.exit(1)

page = next((t for t in tabs if t.get("url", "").startswith("http://127.0.0.1:3001/projects")), tabs[0])
log("page:", page.get("url"))

try:
    import websocket
except ImportError:
    log("FAIL: websocket-client not installed"); proc.kill(); sys.exit(1)

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
msg_id = 0

def cmd(method, params=None):
    global msg_id
    msg_id += 1
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == msg_id:
            return m.get("result", {})

def eval_js(expr):
    r = cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return r.get("result", {}).get("value")

cmd("Runtime.enable")
cmd("Page.enable")

# 3. Wait for the app to load (claims grid renders)
for _ in range(40):
    v = eval_js("document.querySelectorAll('#claims .card').length")
    if v and v >= 5:
        break
    time.sleep(0.5)
log("claims cards rendered:", v)

# 4. Click Run Quick Test (or Run Full Test when FULL=1)
btn_id = 'runFull' if os.environ.get('FULL') == '1' else 'runQuick'
clicked = eval_js("""(() => {
  const btn = document.getElementById('%s');
  if (!btn) return 'no button';
  btn.click(); return 'clicked';
})()""" % btn_id)
log(btn_id + ":", clicked)

# 5. Poll until the score ring settles (scoreNum no longer '-' and not 'Testing…')
start = time.time()
result = None
while time.time() - start < 420:
    num = eval_js("document.getElementById('scoreNum').textContent")
    pct = eval_js("document.getElementById('scorePct').textContent")
    pills = eval_js("document.querySelectorAll('#pills .pill').length")
    if num and num != '–' and pct and 'Testing' not in pct:
        # small settle delay
        time.sleep(2)
        result = {"num": num, "max": eval_js("document.getElementById('scoreMax').textContent"),
                  "pct": pct, "pills": pills}
        break
    time.sleep(3)
else:
    result = {"num": eval_js("document.getElementById('scoreNum').textContent"),
              "max": eval_js("document.getElementById('scoreMax').textContent"),
              "pct": eval_js("document.getElementById('scorePct').textContent"),
              "pills": eval_js("document.querySelectorAll('#pills .pill').length")}

log("SCORE:", json.dumps(result))

# 6. Dump per-claim chips + scores
chips = eval_js("""Array.from(document.querySelectorAll('#claims .card')).map(c => ({
  name: c.querySelector('.name').textContent,
  chip: c.querySelector('.chip').textContent,
  score: (c.querySelector('.score') || {}).textContent || ''
}))""")
log("CLAIMS:", json.dumps(chips, indent=1))

# 7. Improvement cards
improves = eval_js("""Array.from(document.querySelectorAll('.improve')).map(i => {
  const p = i.querySelector('.p'); const b = i.querySelector('b');
  return (p ? p.textContent + ' ' : '') + (b ? b.textContent : '');
})""")
log("IMPROVEMENTS:", json.dumps(improves, indent=1))

ws.close()
proc.terminate()
log("DONE")
