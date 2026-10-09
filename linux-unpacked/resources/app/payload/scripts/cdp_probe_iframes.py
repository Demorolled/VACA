#!/usr/bin/env python3
"""Print the visible text of every colab outputframe iframe."""
import json
import sys
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
n = 0
for t in tabs:
    if t.get("type") != "iframe" or "googleusercontent" not in t.get("url", ""):
        continue
    n += 1
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
        "expression": "document.body ? document.body.innerText.slice(-1200) : '(no body)'",
        "returnByValue": True,
    }}))
    msg = json.loads(ws.recv())
    val = msg.get("result", {}).get("result", {}).get("value", "")
    print("=" * 60)
    print(f"frame {n}: {t['url'][:75]}")
    print(val)
    ws.close()
