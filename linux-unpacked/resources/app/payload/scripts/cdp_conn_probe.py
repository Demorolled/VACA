#!/usr/bin/env python3
"""Definitive Colab connection probe: find connect button / gauges / status across shadow DOMs."""
import json
import sys
import urllib.request
import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if not page:
    print("NO COLAB PAGE FOUND")
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
  const out = { url: location.href.slice(0, 120), buttons: [], gauges: [], statusBar: [] };
  // connect buttons (incl. shadow DOM)
  function walk(root, depth) {
    if (depth > 6) return;
    const all = root.querySelectorAll ? [...root.querySelectorAll('*')] : [];
    for (const el of all) {
      const t = (el.textContent || '').trim();
      if (el.children.length === 0) {
        if (/^Connect(\s|$)/i.test(t) && t.length < 40) out.buttons.push(t.slice(0, 40));
        if (/^RAM:|^Disk:/.test(t) && t.length < 40) out.gauges.push(t);
        if (el.getBoundingClientRect().y > window.innerHeight - 45 && t.length > 2 && t.length < 40) out.statusBar.push(t);
      }
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
    }
  }
  walk(document, 0);
  out.buttons = [...new Set(out.buttons)];
  out.gauges = [...new Set(out.gauges)];
  out.statusBar = [...new Set(out.statusBar)];
  // specific tags
  out.hasConnectBtn = !!document.querySelector('colab-connect-button, #connect, [aria-label*="Connect"]');
  return JSON.stringify(out);
})()"""
print(evaljs(js))
