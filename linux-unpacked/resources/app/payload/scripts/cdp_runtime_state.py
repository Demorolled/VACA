#!/usr/bin/env python3
"""Check Colab connection state: is a runtime connected, what accelerator is selected, what the config cell (cell 2) defines."""
import json
import sys
import urllib.request
import websocket

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if not page:
    print("NO COLAB PAGE FOUND")
    sys.exit(1)

ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
mid = [0]

def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg.get("result", {})

def evaljs(expr):
    r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return r.get("result", {}).get("value")

# Connection state: connect buttons, status text, gauges, toolbar
js = r"""(() => {
  const txt = document.body.innerText || '';
  const out = { connectBtn: false, connTexts: [], gauges: [] };
  for (const el of document.querySelectorAll('button, [role=button], colab-connect-button, colab-google-drive-button')) {
    const t = (el.textContent || '').trim();
    if (/^Connect(\s|$)/i.test(t)) { out.connectBtn = true; out.connectBtnText = t.slice(0, 40); }
  }
  const seen = new Set();
  function walk(root) {
    if (seen.has(root)) return; seen.add(root);
    const all = root.querySelectorAll ? [...root.querySelectorAll('*')] : [];
    for (const el of all) {
      const t = (el.textContent || '').trim();
      if (/^RAM:|^Disk:/.test(t) && el.children.length <= 2) out.gauges.push(t);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  }
  walk(document);
  out.gauges = [...new Set(out.gauges)];
  for (const pat of ['Reconnect', 'Reconnecting', 'Connected', 'Runtime disconnected', 'Connect to hosted runtime', 'Connect to a hosted runtime', 'Cancel and ignore', 'T4 GPU', 'No accelerator']) {
    if (txt.includes(pat)) out.connTexts.push(pat + ' => YES');
  }
  return JSON.stringify(out);
})()"""
print("CONN:", evaljs(js))
print()

# Config cell 2 full text (defines LR / EPOCHS)
js2 = r"""(() => {
  const cells = [...document.querySelectorAll('.cell.code.notebook-cell')];
  const c = cells[2];
  return c ? (c.innerText || '').slice(0, 2500) : 'no cell 2';
})()"""
print("CELL2 (config):")
print(evaljs(js2))
print()

# GPU-check cell (cell 1) source + output
js3 = r"""(() => {
  const cells = [...document.querySelectorAll('.cell.code.notebook-cell')];
  const c = cells[1];
  if (!c) return 'no cell 1';
  const src = (c.innerText || '').slice(0, 300);
  const ifr = [...c.querySelectorAll('iframe')].length;
  return JSON.stringify({ src: src.replace(/\n/g, ' | '), iframes: ifr });
})()"""
print("CELL1 (gpu check):", evaljs(js3))
