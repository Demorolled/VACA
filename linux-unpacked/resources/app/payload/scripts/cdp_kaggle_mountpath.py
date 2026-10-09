#!/usr/bin/env python3
"""Click 'Copy file path' on the attached dataset to learn the real mount path."""
import json
import sys
import time
import urllib.request
import websocket

EDITOR_URL = "https://www.kaggle.com/code/stevenawoods/vaca-qlora-round6/edit"

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page"), None)
if not page:
    print("NO PAGE FOUND")
    sys.exit(1)

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
mid = [0]

def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg.get("result", {})

def evaljs(expr):
    r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    v = r.get("result", {})
    return v.get("value") if v.get("type") == "string" else v

cur = evaljs("location.href")
if "vaca-qlora-round6" not in (cur or ""):
    call("Page.navigate", {"url": EDITOR_URL})
    time.sleep(16)

# Find and click the "Copy file path" element
click = r"""(() => {
  const els = [...document.querySelectorAll('[aria-label], [role=button], button')];
  const t = els.find(e => e.offsetParent !== null && /Copy file path/.test(e.getAttribute('aria-label') || ''));
  if (t) { t.click(); return 'clicked copy-file-path'; }
  return 'not found';
})()"""
print("CLICK:", evaljs(click))
time.sleep(2)

# Read clipboard via navigator.clipboard
clip = r"""(() => {
  try {
    return navigator.clipboard.readText().then(t => 'CLIPBOARD: ' + t);
  } catch (e) { return 'clipboard read failed: ' + e.message; }
})()"""
r = call("Runtime.evaluate", {"expression": clip, "returnByValue": True, "awaitPromise": True})
v = r.get("result", {})
print("RESULT:", v.get("value") if v.get("type") == "string" else json.dumps(v)[:300])
