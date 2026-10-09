#!/usr/bin/env python3
"""Probe Colab: runtime indicator text, connection banners, RAM/Disk gauges, and config-cell contents."""
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

# 1. Connection/runtime banners + gauges
js1 = r"""(() => {
  const out = { gauges: [], banners: [] };
  const seen = new Set();
  function walk(root) {
    if (seen.has(root)) return; seen.add(root);
    const all = root.querySelectorAll ? [...root.querySelectorAll('*')] : [];
    for (const el of all) {
      const t = (el.textContent||'').trim();
      if (/^RAM:|^Disk:/.test(t) && el.children.length <= 2) out.gauges.push(t);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  }
  walk(document);
  out.gauges = [...new Set(out.gauges)];
  // banners / dialogs
  const txt = document.body.innerText || '';
  for (const pat of ['Runtime disconnected', 'Reconnect', 'Connect to a hosted runtime', 'Connect to runtime', 'Session ended', 'Session expired', 'unavailable', 'GPU quota', 'queued', 'Starting up', 'No GPU', 'Your session crashed', 'crash']) {
    if (txt.includes(pat)) out.banners.push(pat);
  }
  // kernel indicator text near top right
  const tops = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && e.getBoundingClientRect().y < 60 && /(?:RAM|Disk|T4|L4|CPU|GPU|Runtime)/.test((e.textContent||'').trim()));
  out.topTexts = tops.slice(0, 8).map(e => e.textContent.trim().slice(0, 60));
  return JSON.stringify(out);
})()"""
print("RUNTIME:", evaljs(js1))
print()

# 2. Config cell contents (cells that define LR / EPOCHS / DATASET)
js2 = r"""(() => {
  const cells = [...document.querySelectorAll('.cell.code.notebook-cell')];
  return JSON.stringify(cells.map((c, i) => {
    const src = (c.innerText || '').slice(0, 220);
    return { i, src: src.replace(/\n/g, ' | ') };
  }));
})()"""
res = evaljs(js2)
try:
    cells = json.loads(res)
    for c in cells:
        if 'LR' in c['src'] or 'EPOCHS' in c['src'] or 'MAX_SEQ' in c['src'] or 'round6' in c['src'].lower():
            print(f"[{c['i']}] {c['src']}")
except Exception as e:
    print("parse err", e, res[:500])
