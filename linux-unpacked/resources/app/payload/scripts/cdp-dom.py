#!/usr/bin/env python3
"""Inspect Colab page DOM: iframes, body children, element count."""
import json
import urllib.request

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
ws_url = page["webSocketDebuggerUrl"]

import websocket

ws = websocket.create_connection(ws_url, timeout=15)
expr = """
(() => {
  const r = {};
  r.iframes = [...document.querySelectorAll('iframe')].map(f => f.src.slice(0, 80));
  r.bodyChildren = document.body ? document.body.children.length : -1;
  r.bodyHTML = document.body ? document.body.innerHTML.slice(0, 500) : 'NO BODY';
  r.colabEl = !!document.querySelector('colab-loading-pane, colab-workspace, colab-app');
  r.scripts = document.scripts.length;
  r.metaRefresh = document.querySelector('meta[http-equiv="refresh"]') ? document.querySelector('meta[http-equiv="refresh"]').content : null;
  return JSON.stringify(r);
})()
"""
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "{}")
print(json.dumps(json.loads(val), indent=1))
ws.close()
