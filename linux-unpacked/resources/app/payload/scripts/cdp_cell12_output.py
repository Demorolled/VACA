#!/usr/bin/env python3
"""Inspect cell 12's output region in the Colab page DOM."""
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
    "(() => { const cells = [...document.querySelectorAll('.cell.notebook-cell')]; "
    "const c = cells[12]; if (!c) return 'no cell12'; "
    "const ifr = [...c.querySelectorAll('iframe')].map(f => ({ src: (f.src||'').slice(0,70) })); "
    "const pres = [...c.querySelectorAll('pre')].map(p => (p.innerText||'').slice(0,200)); "
    "const outArea = c.querySelector('.output, .codecell-output, .outputarea, .cell-output') || null; "
    "return JSON.stringify({ ifr, pres, outAreaHTML: outArea ? outArea.innerHTML.slice(0,300) : null, "
    "cls: c.className.slice(0,80) }); })()"
)
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "")
print(val[:2000])
ws.close()
