#!/usr/bin/env python3
"""Replace cell 12 with a SINGLE-LINE diagnostic cell (exec('...') with \\n
escapes) so CodeMirror's paste auto-indent cannot mangle it. Tests:
   1. does `python -u -c` subprocess run + print (kernel not wedged)?
   2. does subprocess output stream into the cell (uncaptured)?
   3. is huggingface.co reachable from the runtime? hf-mirror.com? google.com?
   4. does the kernel load torch + CUDA?
"""
import json
import sys
import time
import urllib.request

import websocket

NEW_CODE = r'''exec("import os, subprocess, sys, time\nprint('=== DIAG START ===', flush=True)\nimport torch\nprint('torch', torch.__version__, 'cuda', torch.cuda.is_available(), flush=True)\nr1 = subprocess.run(['python', '-u', '-c', 'print(7*11)'], timeout=90, capture_output=True, text=True)\nprint('subproc-captured rc', r1.returncode, 'out:', (r1.stdout or '').strip()[:80], 'err:', (r1.stderr or '').strip()[:120], flush=True)\nr2 = subprocess.run(['python', '-u', '-c', 'print(7*13)'], timeout=90)\nprint('subproc-streamed rc', r2.returncode, flush=True)\nimport urllib.request\nfor url in ['https://huggingface.co/Orion-zhen/Qwen2.5-7B-Instruct-Uncensored/resolve/main/config.json', 'https://hf-mirror.com/Orion-zhen/Qwen2.5-7B-Instruct-Uncensored/resolve/main/config.json', 'https://www.google.com']:\n    try:\n        t = time.time()\n        st = urllib.request.urlopen(url, timeout=12).status\n        print('NET', url, st, round(time.time() - t, 1), 's', flush=True)\n    except Exception as e:\n        print('NET', url, 'FAIL', repr(e)[:110], flush=True)\nprint('=== DIAG DONE ===', flush=True)")'''

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
print("cell now (should be ONE long line):")
print(cur[:800])
print("...")
print(cur[-200:])
ws.close()
