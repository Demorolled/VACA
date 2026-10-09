#!/usr/bin/env python3
"""Extract detailed console output from the round-6 Kaggle kernel page."""
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
    time.sleep(12)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  // Find sections: cell inputs/outputs. Kaggle renders cells with output below.
  const idx = [];
  lines.forEach((l, i) => { if (/Step \d|CUDA|GPU:|Error|Traceback|unsloth|pip install|Collecting|Successfully|Temporary failure|name resolution|Running|elapsed|ETA/.test(l)) idx.push(i); });
  const window = 200;
  const selected = new Set();
  for (const i of idx) for (let j = Math.max(0, i - 1); j < Math.min(lines.length, i + 8); j++) selected.add(j);
  const out = [];
  for (const j of [...selected].sort((a, b) => a - b)) {
    const l = lines[j];
    if (l.length < 250) out.push((out.length ? '' : '') + l);
  }
  return JSON.stringify({ totalLines: lines.length, hasErrorWord: /Traceback|Error:|KernelWorkerStatus.ERROR|FAILED/.test(txt), out: out.slice(0, 80) });
})()"""
print(evaljs(js))
