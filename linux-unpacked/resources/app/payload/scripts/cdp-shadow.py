#!/usr/bin/env python3
"""List interactive elements across shadow DOM roots in the Colab page."""
import json
import urllib.request

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page"), None)
ws_url = page["webSocketDebuggerUrl"]

import websocket

ws = websocket.create_connection(ws_url, timeout=15)

expr = """
(() => {
  const out = [];
  const seen = new Set();
  function walk(root, depth) {
    const all = root.querySelectorAll('*');
    for (const el of all) {
      if (seen.has(el)) continue;
      seen.add(el);
      const role = el.getAttribute && el.getAttribute('role');
      const tag = el.tagName;
      const isButton = role === 'button' || role === 'menuitem' || tag === 'BUTTON' || tag === 'A';
      if (isButton) {
        const t = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
        if (t) out.push({ d: depth, tag, role, text: t, cls: (el.className || '').toString().slice(0, 40) });
      }
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
    }
    // include shadow roots of this root's direct host children
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
    }
  }
  walk(document, 0);
  return JSON.stringify(out.slice(0, 80));
})()
"""
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "[]")
try:
    items = json.loads(val)
    for i in items:
        print(f"  [{i['d']}] <{i['tag']} role={i.get('role')}> {i['text']}  :: {i.get('cls')}")
except Exception as e:
    print("parse err", e, val[:300])
ws.close()
