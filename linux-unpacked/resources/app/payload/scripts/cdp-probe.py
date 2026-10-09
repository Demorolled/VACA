#!/usr/bin/env python3
"""Probe the Colab page for login state markers."""
import json
import sys
import urllib.request

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws_url = page["webSocketDebuggerUrl"]

import websocket

ws = websocket.create_connection(ws_url, timeout=15)
expr = """
(() => {
  const t = document.body ? document.body.innerText : '';
  return JSON.stringify({
    ready: document.readyState,
    url: location.href,
    title: document.title,
    hasSignIn: t.includes('Sign in') || t.includes('Sign In'),
    hasRecent: t.includes('Recent'),
    hasUpload: t.includes('Upload'),
    bodyLen: t.length,
    head: t.slice(0, 300),
  });
})()
"""
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "{}")
print(json.dumps(json.loads(val), indent=1))
ws.close()
