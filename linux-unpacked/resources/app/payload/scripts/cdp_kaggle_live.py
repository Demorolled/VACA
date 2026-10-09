#!/usr/bin/env python3
"""Read live output of the running Kaggle round-6 kernel from the editor page."""
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

# Ensure on the kernel page (reload if on log view)
cur = evaljs("location.href")
if "vaca-qlora-round6" not in (cur or ""):
    call("Page.navigate", {"url": URL})
    time.sleep(10)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const out = { running: /Running|queued|Complete/i.test(txt) };
  const interesting = lines.filter(l =>
    /CUDA|GPU|Dataset|rows|Unsloth|Unsloth|Loading|Trainable|loss|step|epoch|ETA|GGUF|adapter|results|Error|error|Traceback|%\|/i.test(l) && l.length < 200
  ).slice(0, 50);
  out.hits = interesting;
  return JSON.stringify(out);
})()"""
print(evaljs(js))
