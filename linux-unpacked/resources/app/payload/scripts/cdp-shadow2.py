#!/usr/bin/env python3
"""Find 'New notebook' and upload controls in the Colab homepage shadow DOM."""
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
    if (seen.has(root)) return;
    seen.add(root);
    const all = (root.querySelectorAll ? root.querySelectorAll('*') : []);
    for (const el of all) {
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
      const t = (el.textContent || '').trim().replace(/\\s+/g, ' ');
      const aria = (el.getAttribute('aria-label') || '');
      const title = (el.getAttribute('title') || '');
      const hay = (t + ' ' + aria + ' ' + title).toLowerCase();
      if (hay.includes('new notebook') || hay.includes('upload') || hay.includes('import')) {
        const role = el.getAttribute('role');
        const tag = el.tagName;
        if (tag !== 'DIV' || role) {
          out.push({ d: depth, tag, role, text: t.slice(0, 50), aria: aria.slice(0, 50), title: title.slice(0, 40) });
        }
      }
    }
  }
  walk(document, 0);
  return JSON.stringify(out.slice(0, 30));
})()
"""
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "[]")
try:
    for i in json.loads(val):
        print(f"  [{i['d']}] <{i['tag']} role={i.get('role')}> text={i['text']!r} aria={i['aria']!r} title={i['title']!r}")
except Exception as e:
    print("err", e, val[:400])
ws.close()
