#!/usr/bin/env python3
"""Check the Colab tab for blocking dialogs, the RotateCookies iframe, and any
runtime-disconnect overlays that could silently stall execution."""
import json
import sys
import urllib.request

import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))

# 1. Main page: look for dialogs / overlays / toasts
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page:
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
    expr = (
        "(() => { "
        "const dialogs = [...document.querySelectorAll('[role=dialog], .goog-dialog, dialog, paper-dialog, md-dialog, colab-dialog')]"
        ".map(d => (d.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120)); "
        "const overlay = document.querySelector('.modal-backdrop, .overlay, colab-modal') ? 'OVERLAY PRESENT' : null; "
        "const toast = [...document.querySelectorAll('*')].filter(e => /disconnect|reconnect|rate.?limit|busy/i.test((e.textContent||'')) && e.children.length < 3).slice(0,4).map(e => e.textContent.trim().slice(0,80)); "
        "return JSON.stringify({ dialogs, overlay, toast }); })()"
    )
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
    msg = json.loads(ws.recv())
    print("MAIN PAGE:", msg.get("result", {}).get("result", {}).get("value", "{}"))
    ws.close()

# 2. RotateCookies iframe
for t in tabs:
    if t.get("type") == "iframe" and "RotateCookies" in t.get("url", ""):
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": "document.body ? document.body.innerText.slice(0, 600) : '(no body)'",
            "returnByValue": True,
        }}))
        msg = json.loads(ws.recv())
        print("ROTATE COOKIES IFRAME:", msg.get("result", {}).get("result", {}).get("value", "")[:600])
        ws.close()
