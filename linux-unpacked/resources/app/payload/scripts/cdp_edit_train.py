#!/usr/bin/env python3
"""Replace cell 12 with a SINGLE-LINE exec() cell (auto-indent-safe) that:
   - sets HF timeouts so a stalled download errors instead of hanging forever
   - runs the trainer as a subprocess with stdout=PIPE
   - relays the child's output LINE-BY-LINE through the kernel's stdout
     (which renders) because Colab swallows raw subprocess stdout
   - prints an nvidia-smi GPU-utilization heartbeat every 60s so a silent
     stall is distinguishable from healthy training
The editor is Monaco; it must be scrolled into view before clicks land.
"""
import json
import sys
import time
import urllib.request

import websocket

NEW_CODE = r'''exec("import os, subprocess, sys, time, threading\nos.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '120'\nos.environ['HF_HUB_ETAG_TIMEOUT'] = '60'\nos.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'\nprint('wrapper: starting trainer, line-relay output + GPU heartbeat', flush=True)\ncmd = ['python', '-u', '/content/train_round1.py', '--dataset', '/content/dataset/round6-bible-10h.jsonl', '--out-dir', '/content/out', '--rounds', '1', '--start-round', '6', '--lr', str(LR), '--epochs', str(EPOCHS), '--max-seq-length', '2048']\nprint('CMD ' + ' '.join(cmd), flush=True)\ndef gpu():\n    while True:\n        time.sleep(60)\n        try:\n            r = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader'], capture_output=True, text=True, timeout=20)\n            print('GPU> ' + (r.stdout or '').strip()[:70], flush=True)\n        except Exception as e:\n            print('GPU> ERR ' + repr(e)[:70], flush=True)\nthreading.Thread(target=gpu, daemon=True).start()\np = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True)\nfor line in p.stdout:\n    print(line.rstrip(), flush=True)\nrc = p.wait()\nprint('trainer exited rc ' + str(rc), flush=True)")'''

EXPECT = 'line-relay output + GPU heartbeat'

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


def cell_source():
    return evaljs(
        "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; if (!c) return ''; "
        "const ed = c.querySelector('.editor, colab-editor-renderer'); "
        "return ed ? (ed.innerText || '') : (c.innerText || '').split('Step')[0]; })()"
    ) or ""


def click_point():
    return evaljs(
        "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; if (!c) return null; "
        "const ed = c.querySelector('.editor, colab-editor-renderer'); "
        "if (!ed) return null; "
        "const ta = ed.querySelector('textarea'); "
        "const r = (ta && ta.getBoundingClientRect().height > 2) ? ta.getBoundingClientRect() : ed.getBoundingClientRect(); "
        "return JSON.stringify({ x: Math.round(r.x + r.width / 2), y: Math.round(r.y + Math.max(3, r.height / 2)) }); })()"
    )


def focus_editor():
    # scroll the editor itself into the viewport first
    evaljs(
        "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; const ed = c ? c.querySelector('.editor, colab-editor-renderer') : null; "
        "if (ed) ed.scrollIntoView({block:'center'}); return 'ok'; })()"
    )
    time.sleep(0.9)
    pos = click_point()
    if not pos:
        return False
    p = json.loads(pos)
    if p["y"] < 60 or p["y"] > 900:  # off-screen guard
        return False
    mouseclick(p["x"], p["y"])
    time.sleep(0.9)
    foc = evaljs("(() => { const a = document.activeElement; return a ? a.tagName + '.' + (a.className||'').toString().slice(0,40) : 'none'; })()")
    print("  activeElement:", foc)
    return True


evaljs("(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; const c = cells[5]; if (c) c.scrollIntoView({block:'start'}); return 'ok'; })()")
time.sleep(1.0)

# --- Use Monaco's API directly: deterministic setValue on the right editor ---
js = (
    "(() => { const m = monaco; if (!m || !m.editor) return 'no monaco'; "
    "const eds = m.editor.getEditors(); "
    "const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const target = eds.find(e => { const d = e.getDomNode(); return d && d.closest('.cell.code.notebook-cell') === cells[5]; }); "
    "if (!target) return 'no target editor'; "
    "target.setValue(" + json.dumps(NEW_CODE) + "); "
    "return 'setValue ok, len ' + target.getValue().length; })()"
)
res = evaljs(js)
print("monaco setValue:", res)
time.sleep(0.8)

src = cell_source()
if EXPECT in src:
    print("REPLACED OK")
    print("cell source head:", src[:130])
    print("cell source tail:", src[-130:])
else:
    print("setValue did not land; src len", len(src))
    print("src head:", src[:130])
ws.close()
