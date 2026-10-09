#!/usr/bin/env python3
"""Minimal CDP driver for the Colab automation tab.

Usage:
  python3 scripts/cdp_drive.py nav <url>
  python3 scripts/cdp_drive.py eval <js>
  python3 scripts/cdp_drive.py click <css-selector>          # JS click
  python3 scripts/cdp_drive.py clicktext <substring>         # click el whose text contains it
  python3 scripts/cdp_drive.py setfile <css-selector> <path> # DOM.setFileInputFiles
  python3 scripts/cdp_drive.py key <key>                     # Input.dispatchKeyEvent (Enter, Control+Enter...)
  python3 scripts/cdp_drive.py keys <text>                   # Input.insertText
  python3 scripts/cdp_drive.py screenshot <out.png>
  python3 scripts/cdp_drive.py title
  python3 scripts/cdp_drive.py cellout <startIdx>            # text of the cell output panels, JSON
"""
import base64
import json
import sys
import time
import urllib.request

import websocket  # websocket-client


def get_page_ws():
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    page = next(
        (t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")),
        None,
    )
    if page is None:
        print("NO COLAB TAB FOUND", file=sys.stderr)
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
        url = sys.argv[2]
        rpc(ws, "Page.navigate", {"url": url})
        print("navigated")
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
            "const clickable = el.closest('[role=menuitem],[role=button],button,a,.goog-menu-button,[tabindex]') || el; "
            "clickable.click(); return 'clicked: ' + clickable.tagName + ' ' + clickable.textContent.trim().slice(0,40); })()"
            % json.dumps(sub)
        )
        msg = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        print(msg.get("result", {}).get("result", {}).get("value"))
    elif cmd == "setfile":
        sel, path = sys.argv[2], sys.argv[3]
        doc = rpc(ws, "DOM.getDocument", {"depth": -1})
        root = doc["result"]["root"]["nodeId"]
        q = rpc(ws, "DOM.querySelector", {"nodeId": root, "selector": sel})
        node_id = q["result"].get("nodeId")
        if not node_id:
            print("NODE NOT FOUND:", sel)
        else:
            r = rpc(ws, "DOM.setFileInputFiles", {"nodeId": node_id, "files": [path]})
            print("files set" if "error" not in r else r["error"])
    elif cmd == "key":
        key = sys.argv[2]
        if key == "Enter":
            code, k, mods = "Enter", "Enter", 0
        elif key == "Control+Enter":
            code, k, mods = "Enter", "Enter", 2  # 2 = ctrl
        else:
            code, k, mods = key, key, 0
        rpc(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": k, "code": code,
                                            "modifiers": mods, "windowsVirtualKeyCode": 13 if k == "Enter" else 0})
        rpc(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": k, "code": code,
                                            "modifiers": mods, "windowsVirtualKeyCode": 13 if k == "Enter" else 0})
        print("key sent")
    elif cmd == "keys":
        rpc(ws, "Input.insertText", {"text": sys.argv[2]})
        print("text inserted")
    elif cmd == "mouseclicktext":
        # real mouse click on the leaf element whose text contains <sub>
        sub = sys.argv[2]
        js = (
            "(() => { const els = [...document.querySelectorAll('*')]; "
            "const el = els.find(e => e.children.length === 0 && e.textContent.trim().includes(%s)); "
            "if (!el) return JSON.stringify({ok:false}); "
            "const r = el.getBoundingClientRect(); "
            "return JSON.stringify({ok:true, x: r.x + r.width/2, y: r.y + r.height/2, tag: el.tagName}); })()"
            % json.dumps(sub)
        )
        msg = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        try:
            info = json.loads(msg.get("result", {}).get("result", {}).get("value", "{}"))
        except Exception:
            info = {}
        if not info.get("ok"):
            print("NOT FOUND:", sub)
        else:
            x, y = info["x"], info["y"]
            rpc(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                                "button": "left", "clickCount": 1})
            rpc(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                                 "button": "left", "clickCount": 1})
            print(f"mouse-clicked {info['tag']} at ({x:.0f},{y:.0f})")
    elif cmd == "screenshot":
        msg = rpc(ws, "Page.captureScreenshot", {"format": "png"})
        data = msg["result"]["data"]
        open(sys.argv[2], "wb").write(base64.b64decode(data))
        print("saved", sys.argv[2])
    elif cmd == "title":
        msg = rpc(ws, "Runtime.evaluate",
                  {"expression": "document.title + ' | ' + location.href", "returnByValue": True})
        print(msg.get("result", {}).get("result", {}).get("value"))
    elif cmd == "cellout":
        # grab all <pre> outputs in the notebook (Colab renders outputs in pre.output)
        msg = rpc(
            ws,
            "Runtime.evaluate",
            {
                "expression": (
                    "(() => { const pres = [...document.querySelectorAll('pre, .output, .codecell-output')]; "
                    "const out = []; "
                    "pres.forEach(p => { const t = p.innerText || p.textContent || ''; if (t.trim()) out.push(t.slice(0, 400)); }); "
                    "return JSON.stringify(out.slice(0, 12)); })()"
                ),
                "returnByValue": True,
            },
        )
        try:
            val = json.loads(msg.get("result", {}).get("result", {}).get("value", "[]"))
            for i, t in enumerate(val):
                print(f"--- output[{i}] ---")
                print(t)
        except Exception:
            print(msg.get("result", {}).get("result", {}).get("value", "")[:500])
    else:
        print("unknown cmd", cmd)
    ws.close()


if __name__ == "__main__":
    main()
