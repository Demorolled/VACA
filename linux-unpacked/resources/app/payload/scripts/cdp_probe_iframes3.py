#!/usr/bin/env python3
"""Deep probe colab outputframes: nested iframes + shadow DOM + text."""
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
            "(() => { const out = { nested: [], shadow: 0, pres: [], txt: '', htmlLen: 0 }; "
            "const b = document.body; if (!b) return JSON.stringify(out); "
            "out.htmlLen = (b.innerHTML || '').length; "
            "out.txt = (b.innerText || '').slice(-2000); "
            "out.nested = [...b.querySelectorAll('iframe')].map(f => (f.src || '').slice(0, 60)); "
            "const walk = (r) => { for (const el of r.querySelectorAll('*')) { if (el.shadowRoot) { out.shadow++; walk(el.shadowRoot); } } }; "
            "walk(b); "
            "out.pres = [...b.querySelectorAll('pre')].map(p => (p.innerText || '').slice(0, 150)); "
            "const bars = [...b.querySelectorAll('progress, [role=progressbar], .progress')].map(p => (p.getAttribute('value')||'') + '/' + (p.getAttribute('max')||'')); "
            "out.bars = bars; "
            "return JSON.stringify(out); })()"
        ),
        "returnByValue": True,
    }}))
    msg = json.loads(ws.recv())
    val = msg.get("result", {}).get("result", {}).get("value", "")
    print("=" * 60)
    print(f"frame {n}: {t['url'][:70]}")
    print(val[:2500])
    ws.close()
