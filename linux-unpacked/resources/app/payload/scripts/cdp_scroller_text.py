#!/usr/bin/env python3
"""Print the tail of the Colab notebook scroller text (what's on screen)."""
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
        "(() => { const s = document.querySelector('colab-scroller') || document.body; "
        "const lines = (s.innerText || '').split('\\n').filter(l => l.trim()); "
        "return JSON.stringify(lines.slice(-50)); })()"
    ),
    "returnByValue": True,
}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "[]")
try:
    for line in json.loads(val):
        print(line[:160])
except Exception as e:
    print("err", e, val[:400])
ws.close()
