#!/usr/bin/env python3
"""Minimal CDP driver for the Lightning AI studio automation tab (Firefox).

Usage:
  python3 scripts/cdp_lightning.py nav <url>
  python3 scripts/cdp_lightning.py eval <js>
  python3 scripts/cdp_lightning.py click <css-selector>
  python3 scripts/cdp_lightning.py clicktext <substring>
  python3 scripts/cdp_lightning.py keys <text>
  python3 scripts/cdp_lightning.py key <Enter|Control+Enter>
  python3 scripts/cdp_lightning.py screenshot <out.png>
  python3 scripts/cdp_lightning.py title
  python3 scripts/cdp_lightning.py tabs

The Lightning studio is a web IDE (VS Code-style). The terminal can be
driven by focusing its xterm/textarea and typing, or by JS eval when the
page exposes one. Firefox exposes a subset of CDP: Runtime.evaluate,
Page.navigate, Input, DOM — which is enough for this flow.
"""
import base64
import json
import sys
import time
import urllib.request

import websocket  # websocket-client

PORT = "9225"


def get_page_ws(port=PORT):
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
    page = next(
        (t for t in tabs
         if t.get("type") in ("page", "webpage") and "lightning" in t.get("url", "")),
        None,
    )
    if page is None:
        print("NO LIGHTNING TAB FOUND", file=sys.stderr)
        for t in tabs:
            print("  -", t.get("type"), t.get("url", "")[:80], file=sys.stderr)
        sys.exit(1)
    return page["webSocketDebuggerUrl"]


def rpc(ws, method, params=None, mid=1):
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg


def main():
    cmd = sys.argv[1]
    ws = websocket.create_connection(get_page_ws(), timeout=30)

    if cmd == "nav":
        rpc(ws, "Page.navigate", {"url": sys.argv[2]})
        print("navigated")
    elif cmd == "tabs":
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
        for t in tabs:
            print(t.get("type"), "|", t.get("url", "")[:100])
    elif cmd == "eval":
        js = sys.argv[2]
        msg = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        res = msg.get("result", {})
        if "exceptionDetails" in res:
            print("EXC:", json.dumps(res["exceptionDetails"])[:500])
        else:
            print(json.dumps(res.get("result", {}).get("value")))
    elif cmd == "click":
        sel = sys.argv[2]
        js = (
            "(() => { const el = document.querySelector(%s); "
            "if (!el) return 'NOT FOUND'; el.click(); return 'clicked'; })()" % json.dumps(sel)
        )
        msg = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        print(msg.get("result", {}).get("result", {}).get("value"))
    elif cmd == "clicktext":
        sub = sys.argv[2]
        js = (
            "(() => { const els = [...document.querySelectorAll('*')]; "
            "const el = els.find(e => e.children.length === 0 && e.textContent.trim().includes(%s)); "
            "if (!el) return 'NOT FOUND'; "
            "const clickable = el.closest('[role=menuitem],[role=button],button,a,[tabindex]') || el; "
            "clickable.click(); return 'clicked: ' + clickable.tagName + ' ' + clickable.textContent.trim().slice(0,40); })()"
            % json.dumps(sub)
        )
        msg = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        print(msg.get("result", {}).get("result", {}).get("value"))
    elif cmd == "keys":
        rpc(ws, "Input.insertText", {"text": sys.argv[2]})
        print("text inserted")
    elif cmd == "key":
        key = sys.argv[2]
        if key == "Control+Enter":
            rpc(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "modifiers": 2})
            rpc(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "modifiers": 2})
        else:
            rpc(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key, "modifiers": 0})
            rpc(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key, "modifiers": 0})
        print("key sent")
    elif cmd == "screenshot":
        msg = rpc(ws, "Page.captureScreenshot", {"format": "png"})
        data = msg["result"]["data"]
        open(sys.argv[2], "wb").write(base64.b64decode(data))
        print("saved", sys.argv[2])
    elif cmd == "title":
        msg = rpc(ws, "Runtime.evaluate",
                  {"expression": "document.title + ' | ' + location.href", "returnByValue": True})
        print(msg.get("result", {}).get("result", {}).get("value"))
    else:
        print("unknown cmd", cmd)
    ws.close()


if __name__ == "__main__":
    main()
