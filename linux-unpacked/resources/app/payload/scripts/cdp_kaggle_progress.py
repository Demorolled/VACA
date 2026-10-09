#!/usr/bin/env python3
"""Force-load the running Kaggle kernel page and extract live output lines."""
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

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=25)
mid = [0]

def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg.get("result", {})

def evaljs(expr, timeout=20):
    call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    v = r.get("result", {})
    return v.get("value") if v.get("type") == "string" else v

# Hard reload to get fresh state
call("Page.navigate", {"url": URL})
time.sleep(16)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  // find meaningful progress lines anywhere in the page
  const out = [];
  for (const l of lines) {
    if (l.length > 300) continue;
    if (/step|loss|epoch|%\|.*\/|Trainable|Loading|adapter|CUDA|GPU|Error|error|Traceback|NameError|rows|dataset|Unsloth|tokens|ETA|saved|GGUF|zip|results|finished|complete/i.test(l)) {
      out.push(l);
    }
  }
  const dedup = out.filter((v, i) => out.indexOf(v) === i);
  const tail = dedup.slice(-50);
  return JSON.stringify({
    href: location.href,
    totalMatching: dedup.length,
    lastLines: tail,
  });
})()"""
print(evaljs(js))
