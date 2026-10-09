#!/usr/bin/env python3
"""Attach the round6-bible-10h dataset to the Kaggle kernel via the web UI."""
import json
import sys
import time
import urllib.request
import websocket

URL = "https://www.kaggle.com/code/stevenawoods/vaca-qlora-round6"

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
    call("Page.navigate", {"url": URL})
    time.sleep(14)

# Inspect the Input panel: is the dataset attached? what does the input UI show?
js = r"""(() => {
  const out = {};
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const ii = lines.findIndex(l => /^Input$/.test(l));
  out.inputBlock = ii >= 0 ? lines.slice(ii, ii + 12) : [];
  // look for "Add Input" buttons / "+" actions
  const adders = [...document.querySelectorAll('button, [role=button], a, [role=tab]')]
    .filter(e => e.offsetParent !== null && /add input|add data|\+ input|attach/i.test((e.textContent||'').trim() + ' ' + (e.getAttribute('aria-label')||'')))
    .map(e => (e.textContent||'').trim().slice(0, 40) + ' | ' + (e.getAttribute('aria-label')||'').slice(0,40));
  out.adders = adders.slice(0, 6);
  return JSON.stringify(out);
})()"""
print("PROBE:", evaljs(js))
