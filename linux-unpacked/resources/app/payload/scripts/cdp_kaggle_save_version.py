#!/usr/bin/env python3
"""Click Save Version in the Kaggle editor to queue a run with the dataset mounted."""
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

# Click Save Version
click = r"""(() => {
  const els = [...document.querySelectorAll('button, [role=button]')];
  const t = els.find(e => e.offsetParent !== null && (e.getAttribute('aria-label')||'').trim() === 'Save Version');
  if (t) { t.click(); return 'clicked Save Version'; }
  const t2 = els.find(e => e.offsetParent !== null && /Save Version/.test((e.textContent||'') + (e.getAttribute('aria-label')||'')));
  if (t2) { t2.click(); return 'clicked Save Version (text)'; }
  return 'no Save Version button';
})()"""
print("1:", evaljs(click))
time.sleep(3)

# Dialog: look for the save form / confirm button
dlg = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const out = { dialogLines: [] };
  // Save version dialog typically has: "Save a new version", "Version title", Save button
  const di = lines.findIndex(l => /save a new version|version title|save and run|save & run/i.test(l));
  out.dialogLines = di >= 0 ? lines.slice(Math.max(0, di - 3), di + 15) : [];
  const btns = [...document.querySelectorAll('button, [role=button]')]
    .filter(e => e.offsetParent !== null)
    .map(e => ((e.getAttribute('aria-label')||'') + ' | ' + (e.textContent||'').trim()).slice(0, 60))
    .filter(x => /save|run|cancel/i.test(x));
  out.buttons = btns.slice(0, 10);
  return JSON.stringify(out);
})()"""
print("2 DIALOG:", evaljs(dlg))

# If there's a "Save" primary button, click it
click2 = r"""(() => {
  const els = [...document.querySelectorAll('button, [role=button]')];
  const t = els.find(e => e.offsetParent !== null && /^Save(\s|$)/i.test((e.textContent||'').trim()) && (e.className||'').toString().toLowerCase().includes('contained') === false && (e.textContent||'').trim().length <= 8);
  if (t) { t.click(); return 'clicked ' + (t.textContent||'').trim(); }
  return 'no plain Save button';
})()"""
print("3:", evaljs(click2))
time.sleep(2)
print("4 STATUS:", evaljs("document.body.innerText.split('\\n').map(s=>s.trim()).filter(l=>/saved|queued|running|version/i.test(l)).slice(0,8)"))
