#!/usr/bin/env python3
"""Click Logs tab + version dropdown on the Kaggle kernel page; read failure text."""
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

# Click the "Logs" tab
click = r"""(() => {
  const els = [...document.querySelectorAll('a, button, [role=tab], div')];
  const t = els.find(e => (e.textContent || '').trim() === 'Logs' && e.offsetParent !== null);
  if (t) { t.click(); return 'clicked Logs'; }
  return 'no Logs tab found';
})()"""
print("LOGSCLICK:", evaljs(click))
time.sleep(4)

# Read the Logs panel content
logs = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const li = lines.findIndex(l => /^(Logs|Error|Error output|Run Log)/.test(l));
  const block = li >= 0 ? lines.slice(li, li + 70) : lines.slice(0, 60);
  return JSON.stringify(block);
})()"""
print("LOGS:", evaljs(logs))

# Also try clicking the version dropdown (shows history)
ver = r"""(() => {
  const els = [...document.querySelectorAll('button, [role=button], div')];
  const t = els.find(e => /^Version .* of .*$/.test((e.textContent || '').trim()) && e.offsetParent !== null);
  if (t) { t.click(); return 'clicked ' + t.textContent.trim(); }
  return 'no version chip';
})()"""
print("VERCLICK:", evaljs(ver))
time.sleep(2)
ver2 = r"""(() => {
  const txt = document.body.innerText || '';
  return JSON.stringify(txt.split('\n').map(s => s.trim()).filter(l => /^v\d+|Version|run -|2026-08|failure|success/i.test(l)).slice(0, 25));
})()"""
print("VERLIST:", evaljs(ver2))
