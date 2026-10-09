#!/usr/bin/env python3
"""One-shot status check for the running Colab training (cell 12).

Usage: python3 scripts/cdp_train_watch.py [--watch N]
  --watch N : sample every 60s, N times (default 1 = single check)

Prints: cell state, current step / total, ETA, GPU util, last loss lines.
"""
import json
import sys
import time
import urllib.request

import websocket


def get_ws():
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
    if page is None:
        print("NO COLAB TAB")
        sys.exit(1)
    return websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)


def sample(ws):
    mid = [0]

    def call(method, params=None):
        mid[0] += 1
        m = mid[0]
        ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == m:
                return msg

    expr = (
        "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
        "const c = cells[5]; if (!c) return 'no cell'; "
        "const pre = c.querySelector('.stream pre'); const t = pre ? pre.innerText : ''; "
        "const last = (re) => { const m = [...t.matchAll(re)]; return m.length ? m[m.length - 1][1] : '?'; }; "
        "const step = last(/\\|[ ]*([0-9]+)\\/662/g); "
        "const eta = last(/<([0-9]+:[0-9]+:[0-9]+)/g); "
        "const rate = last(/,[ ]*([0-9.]+)s\\/it/g); "
        "const gpu = (t.match(/GPU> [^\\n]*/g) || []).slice(-1)[0] || 'no GPU hb yet'; "
        "const loss = (t.match(/loss[^\\n]*/gi) || []).slice(-1)[0] || 'no loss yet'; "
        "return JSON.stringify({ state: c.className.slice(0, 40), step, eta, rate, gpu, loss }); })()"
    )
    msg = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    val = msg.get("result", {}).get("result", {}).get("value", "{}")
    try:
        d = json.loads(val)
    except Exception:
        d = {"raw": val}
    print(
        f"[{time.strftime('%H:%M:%S')}] state={d.get('state')} | step={d.get('step')}/662"
        f" | ETA={d.get('eta')} | {d.get('rate')}s/it\n"
        f"    {d.get('gpu')}\n"
        f"    last loss: {d.get('loss')}"
    )


def main():
    watch = 1
    if len(sys.argv) > 2 and sys.argv[1] == "--watch":
        watch = int(sys.argv[2])
    ws = get_ws()
    for i in range(watch):
        sample(ws)
        if i < watch - 1:
            time.sleep(60)
    ws.close()


if __name__ == "__main__":
    main()
