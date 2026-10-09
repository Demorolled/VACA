#!/usr/bin/env python3
"""Check the Colab train cell (cell 12 / cells[5]) state and output tail via CDP."""
import json
import sys
import urllib.request
import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if not page:
    print("NO COLAB PAGE FOUND - is Chrome running with remote debugging?")
    sys.exit(1)

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
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
    return r.get("result", {}).get("value")

js = r"""(() => {
  const cells = [...document.querySelectorAll('.cell.code.notebook-cell')];
  const c = cells[5];
  if (!c) return 'no cell';
  const pre = c.querySelector('.stream pre');
  const t = pre ? pre.innerText : '';
  const steps = [...t.matchAll(/\|[ ]*([0-9]+)\/662/g)];
  const lastStep = steps.length ? steps[steps.length-1][1] : '?';
  const eta = t.match(/<([0-9]+:[0-9]+:[0-9]+)/);
  const gpu = (t.match(/GPU> [^\n]*/g) || []).slice(-3);
  const lossLines = (t.match(/loss[^\n]*/g) || []).slice(-3);
  const waitCount = (t.match(/WAIT:/g) || []).length;
  const hasGGUF = t.includes('GGUF') || t.includes('quantized') || t.includes('Saved');
  const hasError = t.includes('Traceback') || t.includes('Error');
  const errTail = t.includes('Traceback') ? t.slice(t.lastIndexOf('Traceback'), t.length).slice(0, 1200) : '';
  return JSON.stringify({
    state: c.className.slice(0, 60),
    streamLen: t.length,
    lastStep, eta: eta ? eta[1] : '?',
    gpu, lossLines, waitCount,
    hasGGUF, hasError,
    errTail,
    tail: t.slice(-900)
  });
})()"""

print(evaljs(js))
