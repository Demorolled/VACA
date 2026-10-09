#!/usr/bin/env python3
"""Open the Kaggle kernel editor, probe Input panel, attempt to add the dataset input."""
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

call("Page.navigate", {"url": EDITOR_URL})
time.sleep(16)

js = r"""(() => {
  const out = { url: location.href.slice(0, 140), title: document.title };
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const ii = lines.findIndex(l => /^Input$/.test(l));
  out.inputBlock = ii >= 0 ? lines.slice(ii, ii + 18) : [];
  // Find clickable "Add Input"/"+" elements near the Input section
  const els = [...document.querySelectorAll('button, [role=button], a, [aria-label]')]
    .filter(e => e.offsetParent !== null)
    .map(e => ({ t: (e.textContent||'').trim().slice(0,30), a: (e.getAttribute('aria-label')||'').slice(0,50), cls: (e.className||'').toString().slice(0,30) }))
    .filter(x => /add|input|\+|attach|data/i.test(x.t + ' ' + x.a));
  out.actions = els.slice(0, 10);
  return JSON.stringify(out);
})()"""
print(evaljs(js))
