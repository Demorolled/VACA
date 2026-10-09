#!/usr/bin/env python3
"""Click Colab's Runtime menu then 'Interrupt execution' via CDP."""
import json
import sys
import time
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
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
            return msg


def evaljs(expr):
    msg = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return msg.get("result", {}).get("result", {}).get("value")


def mouseclick(x, y):
    call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


# 1. click the Runtime menu (found at ~283,50)
mouseclick(283, 50)
time.sleep(1.5)

# 2. find the "Interrupt execution" menu item (clickable) and click it
res = evaljs(
    "(() => { const els = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 "
    "&& /interrupt/i.test((e.textContent||''))); "
    "return JSON.stringify(els.slice(0, 5).map(e => { const r = e.getBoundingClientRect(); "
    "return { tag: e.tagName, txt: (e.textContent||'').trim().slice(0,40), x: Math.round(r.x + r.width/2), "
    "y: Math.round(r.y + r.height/2), vis: r.width > 0 }; })); })()"
)
print("interrupt items:", res)
try:
    items = json.loads(res or "[]")
    vis = [i for i in items if i.get("vis")]
    if vis:
        mouseclick(vis[0]["x"], vis[0]["y"])
        print(f"clicked Interrupt at ({vis[0]['x']},{vis[0]['y']})")
    else:
        print("no visible interrupt item found; dumping menu text")
        print(evaljs("(() => { const m = [...document.querySelectorAll('[role=menu], .goog-menu')].map(e => (e.innerText||'').slice(0,400)); return JSON.stringify(m); })()"))
except Exception as e:
    print("err", e)

time.sleep(2)
ws.close()
