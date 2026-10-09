#!/usr/bin/env python3
"""Print the full source of the train cell (index 5 among code cells)."""
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
        "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; return JSON.stringify(c ? c.innerText : 'no cell'); })()"
    ),
    "returnByValue": True,
}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "")
try:
    txt = json.loads(val)
    print(txt)
except Exception:
    print(val)
ws.close()
