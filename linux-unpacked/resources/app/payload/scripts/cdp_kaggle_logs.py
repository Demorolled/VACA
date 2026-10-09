#!/usr/bin/env python3
"""Reload the Kaggle round-6 kernel page; extract Logs + version info."""
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

# Force reload
call("Page.navigate", {"url": URL})
time.sleep(14)

# Grab the Logs panel text (click Logs tab if needed)
js = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const li = lines.findIndex(l => /^Logs$/.test(l));
  const block = li >= 0 ? lines.slice(li, li + 60) : [];
  const vi = lines.findIndex(l => /^Version .* of .*$/.test(l));
  const ver = vi >= 0 ? lines[vi] : '?';
  const runtime = lines.find(l => /run - (failure|success|running)/i.test(l)) || '?';
  return JSON.stringify({ ver, runtime, block });
})()"""
print(evaljs(js))
