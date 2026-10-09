#!/usr/bin/env python3
"""Click the Colab upload widget's 'Choose Files' button and inject a local
file via Page.fileChooserOpened interception.

Usage: python3 scripts/cdp_click_upload.py <x> <y> <local_file>
"""
import json
import sys
import time
import urllib.request

import websocket

x, y = float(sys.argv[1]), float(sys.argv[2])
path = sys.argv[3]

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
mid = [0]


def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg


call("Page.enable")
call("Page.setInterceptFileChooserDialog", {"enabled": True})

# real mouse click on the button
call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
print(f"clicked ({x},{y})")

deadline = time.time() + 40
handled = False
ws.settimeout(3)
while time.time() < deadline:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        continue
    if msg.get("method") == "Page.fileChooserOpened":
        mode = msg["params"].get("mode", "selectSingle")
        call("Page.handleFileChooser", {"files": [path], "mode": mode})
        print(f"file chooser handled ({mode}): {path}")
        handled = True
        break
if not handled:
    print("no fileChooserOpened within 40s")
ws.close()
sys.exit(0 if handled else 1)
