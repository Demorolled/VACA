#!/usr/bin/env python3
"""Dump the train cell's full output container HTML."""
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
expr = (
    "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const c = cells[5]; if (!c) return 'no cell'; "
    "const out = c.querySelector('.output-iframe-container') || c; "
    "return JSON.stringify({ html: out.innerHTML.slice(0, 3000) }); })()"
)
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "")
try:
    d = json.loads(val)
    print(d["html"])
except Exception:
    print(val[:3000])
ws.close()
