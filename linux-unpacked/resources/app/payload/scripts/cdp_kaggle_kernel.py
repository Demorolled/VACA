#!/usr/bin/env python3
"""Open the round-6 Kaggle kernel page and read status + settings + console output."""
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

call("Page.navigate", {"url": URL})
time.sleep(10)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const out = { title: document.title, url: location.href.slice(0, 100) };
  // status chips / buttons
  out.hasRunAll = /Run All|Save Version|Run All \(F9\)/i.test(txt);
  out.hasSettings = /Settings/i.test(txt);
  // console output text (the notebook body shows cell output)
  const body = txt.split('\n').map(s => s.trim()).filter(Boolean);
  out.outputHints = body.filter(l => /CUDA|GPU|pip|unsloth|Error|error|Running|Complete|queued|Step 1|Installing/i.test(l) && l.length < 160).slice(0, 30);
  out.isError = /Error|errored|FAILED/i.test(txt);
  return JSON.stringify(out);
})()"""
print(evaljs(js))
