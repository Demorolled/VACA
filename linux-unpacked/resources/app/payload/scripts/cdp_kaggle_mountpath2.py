#!/usr/bin/env python3
"""Learn the exact /kaggle/input mount path of the attached dataset."""
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

def evaljs(expr, await_promise=False):
    r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": await_promise})
    v = r.get("result", {})
    return v.get("value") if v.get("type") == "string" else v

cur = evaljs("location.href")
if "vaca-qlora-round6" not in (cur or ""):
    call("Page.navigate", {"url": EDITOR_URL})
    time.sleep(16)

# Grant clipboard permissions
perm = call("Browser.grantPermissions", {"origin": "https://www.kaggle.com", "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]})
print("perm:", perm)

# Click Copy file path then read clipboard
click = r"""(() => {
  const els = [...document.querySelectorAll('[aria-label], [role=button], button')];
  const t = els.find(e => e.offsetParent !== null && /Copy file path/.test(e.getAttribute('aria-label') || ''));
  if (t) { t.click(); return 'clicked'; }
  return 'not found';
})()"""
print("click:", evaljs(click))
time.sleep(1.5)

clip = r"""(async () => {
  try {
    const t = await navigator.clipboard.readText();
    return 'CLIPBOARD: ' + t;
  } catch (e) { return 'clip-read-fail: ' + e.message; }
})()"""
print("clip:", evaljs(clip, await_promise=True))

# Dump the full Input panel HTML (text around the dataset row)
html = r"""(() => {
  const els = [...document.querySelectorAll('*')].filter(e => e.offsetParent !== null);
  const ds = els.find(e => /Round 6 Bible/.test(e.getAttribute('aria-label') || '') || /Copy file path/.test(e.getAttribute('aria-label') || ''));
  if (!ds) return 'no dataset row';
  let node = ds;
  for (let i = 0; i < 6 && node.parentElement; i++) node = node.parentElement;
  return (node.innerText || '').slice(0, 800);
})()"""
print("ROW:", evaljs(html))
