#!/usr/bin/env python3
"""Sample Colab RAM/Disk gauges + train-cell stream length to confirm progress.

Samples N times, S seconds apart, and prints the deltas so we can tell if the
runtime is actually doing work (RAM climbing = model load; stream growing =
training output streaming).
"""
import json
import sys
import time
import urllib.request

import websocket

SAMPLE_S = int(sys.argv[1]) if len(sys.argv) > 1 else 60
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 3

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)


def sample():
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
    expr = (
        "(() => { "
        "const all = [...document.querySelectorAll('*')].map(e => (e.textContent||'').trim()); "
        "const ram = all.find(t => /^RAM:/.test(t)); "
        "const disk = all.find(t => /^Disk:/.test(t)); "
        "const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; "
        "const pre = c ? c.querySelector('.stream pre') : null; "
        "const cls = c ? c.className.slice(0, 60) : 'no cell'; "
        "return JSON.stringify({ ram: ram || null, disk: disk || null, "
        "streamLen: pre ? pre.innerText.length : null, cls }); })()"
    )
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
    msg = json.loads(ws.recv())
    val = msg.get("result", {}).get("result", {}).get("value", "{}")
    ws.close()
    return json.loads(val)


for i in range(ROUNDS):
    s = sample()
    print(f"[{time.strftime('%H:%M:%S')}] RAM={s.get('ram')} Disk={s.get('disk')} stream={s.get('streamLen')} cls={s.get('cls')}")
    if i < ROUNDS - 1:
        time.sleep(SAMPLE_S)
