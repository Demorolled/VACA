#!/usr/bin/env python3
"""Open the round-6 Colab notebook in the CDP-controlled Chrome."""
import json
import sys
import time
import urllib.request
import websocket

NOTEBOOK_ID = "1QQuTbZ1-ppx6mgvscJ-bxY9WP6DRQd7w"
URL = f"https://colab.research.google.com/drive/{NOTEBOOK_ID}"

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

# Navigate the tab to the notebook
r = call("Page.navigate", {"url": URL})
print("navigated:", r)

# Wait for load
for i in range(15):
    time.sleep(4)
    r2 = call("Runtime.evaluate", {"expression": "document.title + ' | ' + location.href.slice(0, 100)", "returnByValue": True})
    val = r2.get("result", {}).get("value", "")
    print(f"[{i * 4}s] {val}")
    if "colab.research.google.com/drive" in val and "File Not Found" not in val:
        break
