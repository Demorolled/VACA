#!/usr/bin/env python3
"""Map each code cell's output iframe src (page-side) to spot new streaming frames."""
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
    "return JSON.stringify(cells.map((c, i) => { "
    "const ifr = [...c.querySelectorAll('iframe')].map(f => (f.src || '').slice(0, 90)); "
    "const preTail = [...c.querySelectorAll('pre')].map(p => (p.innerText || '').slice(-120)); "
    "return { i, cls: c.className.slice(0, 60), ifr, preTail: preTail.filter(t => t.trim()).slice(-2) }; })); })()"
)
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "[]")
try:
    for row in json.loads(val):
        print(f"[{row['i']:2d}] {row['cls'][:55]}")
        for f in row["ifr"]:
            print(f"      iframe: {f}")
        for p in row["preTail"]:
            print(f"      out: {p!r}")
except Exception as e:
    print("err", e, val[:400])
ws.close()
