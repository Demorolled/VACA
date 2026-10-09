#!/usr/bin/env python3
"""Verify dataset input attachment in the Kaggle editor + find Save Version/Run All."""
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

js = r"""(() => {
  const out = { url: location.href.slice(0, 140) };
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const ii = lines.findIndex(l => /^Input$/.test(l));
  out.inputBlock = ii >= 0 ? lines.slice(ii, ii + 20) : [];
  // Save Version / Run All buttons
  const saveBtns = [...document.querySelectorAll('button, [role=button]')]
    .filter(e => e.offsetParent !== null)
    .map(e => ({ t: (e.textContent||'').trim().slice(0, 40), a: (e.getAttribute('aria-label')||'').slice(0, 50) }))
    .filter(x => /save|version|run all|run/i.test(x.t + ' ' + x.a));
  out.saveBtns = saveBtns.slice(0, 12);
  return JSON.stringify(out);
})()"""
print(evaljs(js))
