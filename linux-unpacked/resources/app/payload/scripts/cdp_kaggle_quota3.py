#!/usr/bin/env python3
"""Extract Kaggle GPU quota + reset info from the settings page, incl. info tooltips."""
import json
import sys
import time
import urllib.request
import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "kaggle" in t.get("url", "")), None)
if not page:
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
if "kaggle.com/settings" not in (cur or ""):
    call("Page.navigate", {"url": "https://www.kaggle.com/settings/account"})
    time.sleep(8)

# Look for reset info: tooltips, aria labels, or the Quotas block with its details
js = r"""(() => {
  const out = { quotaBlock: [], tooltips: [], aria: [] };
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  const qi = lines.findIndex(l => /^Quotas$/.test(l));
  if (qi >= 0) out.quotaBlock = lines.slice(qi, qi + 25);
  // aria labels near quota rows
  for (const el of document.querySelectorAll('[aria-label], [title], [role=tooltip]')) {
    const a = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (a && /quota|reset|week|gpu|hour/i.test(a) && a.length < 200) out.aria.push(a);
  }
  // click each 'info' button next to Kaggle GPU and read the popover
  const infos = [...document.querySelectorAll('button, [role=button]')].filter(b => /info/i.test((b.getAttribute('aria-label')||'') + (b.textContent||'')) );
  out.infoBtnCount = infos.length;
  return JSON.stringify(out);
})()"""
print(evaljs(js))
