#!/usr/bin/env python3
"""Dump each colab outputframe iframe: innerText tail, html length, progress bars."""
import json
import sys
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
n = 0
for t in tabs:
    if t.get("type") != "iframe" or "googleusercontent" not in t.get("url", ""):
        continue
    n += 1
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
        "expression": (
            "(() => { const b = document.body; if (!b) return '(no body)'; "
            "const html = b.innerHTML || ''; const txt = b.innerText || ''; "
            "const bars = [...document.querySelectorAll('progress, .progress, [role=progressbar]')].length; "
            "return JSON.stringify({ txtLen: txt.length, htmlLen: html.length, bars, tail: txt.slice(-1500) }); })()"
        ),
        "returnByValue": True,
    }}))
    msg = json.loads(ws.recv())
    val = msg.get("result", {}).get("result", {}).get("value", "")
    try:
        d = json.loads(val)
        print("=" * 60)
        print(f"frame {n} | text {d['txtLen']} chars | html {d['htmlLen']} | bars {d['bars']}")
        print(d["tail"])
    except Exception as e:
        print("=" * 60)
        print(f"frame {n} | raw: {val[:500]}")
    ws.close()
