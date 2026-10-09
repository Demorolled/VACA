#!/usr/bin/env python3
"""Evaluate JS in the Colab tab via CDP to check login state."""
import json
import sys
import urllib.request

# find the colab page ws url
tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB PAGE TAB FOUND")
    sys.exit(1)
ws_url = page["webSocketDebuggerUrl"]
print("tab:", page["url"][:70], "|", page["title"][:50])

# connect via websocket-client if available
try:
    import websocket  # websocket-client

    ws = websocket.create_connection(ws_url, timeout=10)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": "document.body ? document.body.innerText.slice(0, 600) : 'no body'",
                                   "returnByValue": True}}))
    msg = json.loads(ws.recv())
    val = (msg.get("result", {}).get("result", {}).get("value", ""))
    print("=== COLAB PAGE TEXT (first 600 chars) ===")
    print(val)
    ws.close()
except ImportError:
    print("websocket-client not available — trying 'websockets'")
    import asyncio

    import websockets

    async def run():
        async with websockets.connect(ws_url, max_size=2**22) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                      "params": {"expression": "document.body ? document.body.innerText.slice(0, 600) : 'no body'",
                                                 "returnByValue": True}}))
            msg = json.loads(await ws.recv())
            print("=== COLAB PAGE TEXT (first 600 chars) ===")
            print(msg.get("result", {}).get("result", {}).get("value", ""))

    asyncio.run(run())
