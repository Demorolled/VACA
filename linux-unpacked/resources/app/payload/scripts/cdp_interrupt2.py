#!/usr/bin/env python3
"""Click the now-open Runtime menu's 'Interrupt execution' item via CDP."""
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


res = evaljs(
    "(() => { const hits = [...document.querySelectorAll('[role=menuitem], [role=menuitemcheckbox], .goog-menuitem')]"
    ".filter(e => /interrupt/i.test((e.textContent||''))); "
    "return JSON.stringify(hits.slice(0, 4).map(e => { const r = e.getBoundingClientRect(); "
    "return { tag: e.tagName, txt: (e.textContent||'').trim().slice(0,40), x: Math.round(r.x + r.width/2), "
    "y: Math.round(r.y + r.height/2), vis: r.width > 0 && r.height > 0 }; })); })()"
)
print("menuitems:", res)
try:
    items = json.loads(res or "[]")
    vis = [i for i in items if i.get("vis")]
    if vis:
        mouseclick(vis[0]["x"], vis[0]["y"])
        print(f"clicked interrupt at ({vis[0]['x']},{vis[0]['y']})")
    else:
        print("no visible item — trying keyboard Ctrl+M then I")
        call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "m", "code": "KeyM", "modifiers": 2, "windowsVirtualKeyCode": 77})
        call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "m", "code": "KeyM", "modifiers": 2, "windowsVirtualKeyCode": 77})
        time.sleep(0.3)
        call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "i", "code": "KeyI", "modifiers": 0, "windowsVirtualKeyCode": 73})
        call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "i", "code": "KeyI", "modifiers": 0, "windowsVirtualKeyCode": 73})
        print("sent Ctrl+M I")
except Exception as e:
    print("err", e)
time.sleep(3)
ws.close()
