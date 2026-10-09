#!/usr/bin/env python3
"""Search every CDP target (incl. OOPIF output frames) for an <input type=file>
and inject a local file.

Usage: python3 scripts/cdp_setfile_iframe.py <local_file>
"""
import json
import sys
import urllib.request

import websocket

path = sys.argv[1]

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
frame_targets = [t for t in tabs if t.get("type") in ("page", "iframe")]
print(f"{len(frame_targets)} page/iframe targets")

for t in frame_targets:
    url = t.get("url", "")
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15)
    mid = [0]

    def call(method, params=None):
        mid[0] += 1
        m = mid[0]
        ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == m:
                return msg

    try:
        r = call(
            "Runtime.evaluate",
            {
                "expression": (
                    "(() => { const inputs = [...document.querySelectorAll('input[type=file]')]; "
                    "return JSON.stringify(inputs.map(i => ({ id: i.id, cls: (i.className||'').slice(0,40), "
                    "accept: i.accept, visible: !!(i.offsetWidth || i.offsetHeight), parent: "
                    "(i.parentElement.textContent||'').trim().replace(/\\s+/g,' ').slice(0,60) }))); })()"
                ),
                "returnByValue": True,
            }
        )
        val = r.get("result", {}).get("result", {}).get("value", "[]")
        inputs = json.loads(val) if val else []
        print(f"  target {t['type']:6s} {url[:55]:55s} → {len(inputs)} file input(s)")
        if inputs:
            for inp in inputs:
                print("     ", inp)
            # inject into the first one
            expr = (
                "(() => { const i = document.querySelector('input[type=file]'); "
                "const dt = new DataTransfer(); "
                "const f = new File([new Uint8Array(1)], 'placeholder'); "  # placeholder, replaced by setFileInputFiles
                "i.files = dt.files; return 'input located: ' + i.id; })()"
            )
            call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            # set files via DOM APIs
            doc = call("DOM.getDocument", {"depth": -1})
            root = doc["result"]["root"]["nodeId"]
            q = call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})
            nid = q["result"].get("nodeId")
            if nid:
                res = call("DOM.setFileInputFiles", {"nodeId": nid, "files": [path]})
                print(f"  ✅ injected into {url[:50]} | error: {res.get('error', 'none')}")
                ws.close()
                sys.exit(0)
            # fallback: dispatch change via JS File constructor
            js = (
                "(() => { const i = document.querySelector('input[type=file]'); "
                "if (!i) return 'no input'; "
                "return 'input ready, id=' + i.id; })()"
            )
            call("Runtime.evaluate", {"expression": js, "returnByValue": True})
    except Exception as e:
        print(f"  target {url[:50]}: err {e}")
    ws.close()

print("DONE — no injection performed")
sys.exit(1)
