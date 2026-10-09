#!/usr/bin/env python3
"""Read trigger JS from a file, evaluate it, intercept the native file chooser,
and inject a local file path.

Usage: python3 scripts/cdp_upload.py <trigger_js_file> <local_file_path>
"""
import json
import sys
import time
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page"), None)
if page is None:
    print("NO PAGE TAB")
    sys.exit(1)
ws_url = page["webSocketDebuggerUrl"]

js_file, path = sys.argv[1], sys.argv[2]
trigger_js = open(js_file, encoding="utf-8").read()

ws = websocket.create_connection(ws_url, timeout=20)
mid = [0]


def call(ws, method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg


call(ws, "Page.enable")
call(ws, "Page.setInterceptFileChooserDialog", {"enabled": True})
res = call(ws, "Runtime.evaluate", {"expression": trigger_js, "returnByValue": True})
print("trigger result:", res.get("result", {}).get("result", {}).get("value"))

deadline = time.time() + 25
handled = False
ws.settimeout(3)
while time.time() < deadline:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        continue
    if msg.get("method") == "Page.fileChooserOpened":
        mode = msg["params"].get("mode", "selectSingle")
        call(ws, "Page.handleFileChooser", {"files": [path], "mode": mode})
        print(f"file chooser handled ({mode}): {path}")
        handled = True
        break
if not handled:
    print("no file chooser event within 25s")
ws.close()
sys.exit(0 if handled else 1)
