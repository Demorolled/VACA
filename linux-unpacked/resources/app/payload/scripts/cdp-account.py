#!/usr/bin/env python3
"""Confirm logged-in account from the OneGoogle bar."""
import json
import urllib.request

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
ws_url = page["webSocketDebuggerUrl"]

import websocket

ws = websocket.create_connection(ws_url, timeout=15)
expr = """
(() => {
  const gb = document.querySelector('.onegoogle');
  const txt = gb ? gb.textContent : '';
  const btn = document.querySelector('a[href*="SignOutOptions"], a[href*="https://accounts.google.com/SignOutOptions"], gb_a');
  return JSON.stringify({
    onegoogleText: txt.slice(0, 400),
    hasSignOutLink: !!document.querySelector('a[href*="SignOutOptions"], a[href*="Logout"]'),
    hasAccountMenu: !!document.querySelector('gb_A, [aria-label*="Google Account"]'),
    ogWidget: !!document.querySelector('iframe[src*="ogs.google.com"]'),
  });
})()
"""
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}}))
msg = json.loads(ws.recv())
val = msg.get("result", {}).get("result", {}).get("value", "{}")
print(json.dumps(json.loads(val), indent=1))
ws.close()
