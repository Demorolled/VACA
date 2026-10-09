#!/usr/bin/env python3
"""Dump the train cell's output container HTML to see how output renders."""
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
    "const c = cells[5]; if (!c) return 'no train cell'; "
    "const out = c.querySelector('.output, .codecell-output, .outputarea, .cell-output'); "
    "return JSON.stringify({ html: out ? out.innerHTML.slice(0, 2000) : null, "
    "frames: [...c.querySelectorAll('iframe')].length, "
    "staticRend: !!c.querySelector('colab-static-output-renderer') }); })()"
)
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "")
print(val[:2500])
ws.close()
