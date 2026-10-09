#!/usr/bin/env python3
"""Report per-cell state from the Colab notebook DOM (surrogate-safe)."""
import json
import sys
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
    "expression": (
        "(() => { const cells = [...document.querySelectorAll('.cell.notebook-cell')]; "
        "return JSON.stringify(cells.map((c, i) => ({ i, cls: c.className.slice(0, 70) }))); })()"
    ),
    "returnByValue": True,
}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "[]")
try:
    for row in json.loads(val):
        print(f"  [{row['i']:2d}] {row['cls']}")
except Exception as e:
    print("err", e, val[:400])
ws.close()
