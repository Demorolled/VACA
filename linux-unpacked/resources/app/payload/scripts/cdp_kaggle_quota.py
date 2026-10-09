#!/usr/bin/env python3
"""Check Kaggle weekly GPU quota via the web UI using the CDP Chrome."""
import json
import sys
import time
import urllib.request
import websocket

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
    if v.get("type") == "string":
        return v.get("value")
    return v

# 1. Go to Kaggle account settings
call("Page.navigate", {"url": "https://www.kaggle.com/settings/account"})
time.sleep(8)

js = r"""(() => {
  const txt = document.body.innerText || '';
  const out = { title: document.title, url: location.href.slice(0, 80), loggedIn: false };
  out.loggedIn = /stevenawoods/i.test(txt);
  // quota-like strings: 'Xh Ym', 'GPU', 'quota', 'hours'
  const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
  out.quotaLines = lines.filter(l => /quota|GPU|TPU|hours?|week|minutes?/i.test(l) && l.length < 120).slice(0, 40);
  out.signin = /Sign in|Log in|Login/i.test(txt) && !out.loggedIn;
  return JSON.stringify(out);
})()"""
print(evaljs(js))
