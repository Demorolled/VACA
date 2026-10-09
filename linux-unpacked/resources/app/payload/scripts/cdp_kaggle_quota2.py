#!/usr/bin/env python3
"""Extract the detailed Kaggle GPU quota numbers from the settings page."""
import json
import sys
import time
import urllib.request
import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "kaggle" in t.get("url", "")), None)
if not page:
    # fall back to any page
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

# Ensure on settings page
cur = evaljs("location.href")
if "kaggle.com/settings" not in (cur or ""):
    call("Page.navigate", {"url": "https://www.kaggle.com/settings/account"})
    time.sleep(8)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  // Find the Quotas section and everything after it up to ~60 lines
  const qi = lines.findIndex(l => /^Quotas$/.test(l));
  const quotaBlock = qi >= 0 ? lines.slice(qi, qi + 60) : [];
  // Any line that looks like a number+unit (hours/minutes/percent) or "GPU" row
  const numeric = lines.filter(l => /(\d+\.?\d*\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|%))|used|limit|remaining|week/i.test(l) && l.length < 100).slice(0, 50);
  return JSON.stringify({ quotaBlock, numeric, hasGPU: /Kaggle GPU/.test(txt), hasTPU: /Kaggle TPU/.test(txt) });
})()"""
print(evaljs(js))
