#!/usr/bin/env python3
"""Replace cell 12's code with a flat (column-0) HF-timeout hardened train
command. Every line is at column 0 so CodeMirror auto-indent cannot mangle it.
"""
import json
import sys
import time
import urllib.request

import websocket

NEW_CODE = (
    "import os, subprocess, sys\n"
    "os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '120'\n"
    "os.environ['HF_HUB_ETAG_TIMEOUT'] = '60'\n"
    "os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'\n"
    "print('HF timeout env set (120s/60s)')\n"
    "cmd = 'python -u train_round1.py --dataset /content/dataset/round6-bible-10h.jsonl --out-dir /content/out --rounds 1 --start-round 6 --lr ' + str(LR) + ' --epochs ' + str(EPOCHS) + ' --max-seq-length 2048'\n"
    "print('PREFIX> ' + cmd)\n"
    "sys.exit(subprocess.call(cmd, shell=True))\n"
)

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
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


def key(k, code, mods=0, vk=0):
    call("Input.dispatchKeyEvent", {"type": "keyDown", "key": k, "code": code, "modifiers": mods, "windowsVirtualKeyCode": vk})
    call("Input.dispatchKeyEvent", {"type": "keyUp", "key": k, "code": code, "modifiers": mods, "windowsVirtualKeyCode": vk})


evaljs("(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; const c = cells[5]; if (c) c.scrollIntoView({block:'center'}); return 'ok'; })()")
time.sleep(1)
pos = evaljs(
    "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const c = cells[5]; const r = c.getBoundingClientRect(); "
    "return JSON.stringify({ x: Math.round(r.x + 60), y: Math.round(r.y + 60) }); })()"
)
print("cell pos:", pos)
try:
    p = json.loads(pos)
    mouseclick(p["x"], p["y"])
except Exception as e:
    print("pos err", e)
time.sleep(1.5)

key("a", "KeyA", 2, 65)  # Ctrl+A select all
time.sleep(0.6)
r = call("Input.insertText", {"text": NEW_CODE})
print("insertText err:", r.get("error", "none"))
time.sleep(0.5)

cur = evaljs(
    "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const c = cells[5]; return JSON.stringify(c ? c.innerText : ''); })()"
)
print("cell now:")
print(cur[:1200])
ws.close()
