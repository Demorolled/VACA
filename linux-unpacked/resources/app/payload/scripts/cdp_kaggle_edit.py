#!/usr/bin/env python3
"""Open the Kaggle kernel editor and probe the Input panel for dataset attachment."""
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

# Click the Edit button (top-right of the kernel page)
click = r"""(() => {
  const els = [...document.querySelectorAll('a, button, [role=button], [role=tab]')];
  const t = els.find(e => (e.textContent || '').trim() === 'Edit' && e.offsetParent !== null);
  if (t) { t.click(); return 'clicked Edit: ' + t.href; }
  return 'no Edit button';
})()"""
print("EDIT:", evaljs(click))
time.sleep(12)

# After entering editor, probe for Input / Add Input
js = r"""(() => {
  const out = { url: location.href.slice(0, 130), inputBlock: [], adders: [] };
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const ii = lines.findIndex(l => /^Input$/.test(l));
  out.inputBlock = ii >= 0 ? lines.slice(ii, ii + 15) : [];
  const adders = [...document.querySelectorAll('button, [role=button], a, [role=tab], [aria-label]')]
    .filter(e => e.offsetParent !== null && /add input|add data|attach|input/i.test((e.getAttribute('aria-label')||'') + ' ' + (e.textContent||'').trim()))
    .slice(0, 8)
    .map(e => ((e.getAttribute('aria-label')||'') + ' | ' + (e.textContent||'').trim()).slice(0, 60));
  out.adders = adders;
  return JSON.stringify(out);
})()"""
print("EDITOR:", evaljs(js))
