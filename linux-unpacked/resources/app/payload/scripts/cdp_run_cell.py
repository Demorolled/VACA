#!/usr/bin/env python3
"""Run a specific Colab cell by index via CDP, with optional file upload.

Usage:
  python3 scripts/cdp_run_cell.py <cell_index> [--file <path>] [--timeout <s>]
      cell_index : notebook cell number (matches the cell's aria-label "Cell N")
      --file     : if given, arm Page.setInterceptFileChooserDialog BEFORE
                   clicking so the dataset upload prompt gets the local file
      --timeout  : seconds to wait for a fileChooserOpened event (default 60)

After clicking, the script prints the cell's current output text (first 1500
chars) so the caller can see whether it started, errored, or finished.
"""
import argparse
import json
import sys
import time
import urllib.request

import websocket


def get_colab_ws():
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    page = next(
        (t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")),
        None,
    )
    if page is None:
        print("NO COLAB TAB FOUND", file=sys.stderr)
        sys.exit(1)
    return page["webSocketDebuggerUrl"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cell_index", type=int)
    ap.add_argument("--file", default=None)
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    ws = websocket.create_connection(get_colab_ws(), timeout=30)
    mid = [0]

    def call(method, params=None):
        mid[0] += 1
        m = mid[0]
        ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == m:
                return msg

    def cell_js(idx):
        return (
            "(() => { const runs = [...document.querySelectorAll('colab-run-button')]; "
            "const run = runs[%d]; "
            "if (!run) return 'NOT FOUND: no colab-run-button[%d]'; "
            "const root = run.shadowRoot || run; "
            "const btn = root.querySelector('button[aria-label=\"Run cell\"]') || root.querySelector('button'); "
            "if (!btn) return 'NOT FOUND: no button in shadow root'; "
            "btn.click(); return 'clicked run btn for cell %d'; })()"
            % (idx, idx, idx)
        )

    call("Page.enable")
    if args.file:
        call("Page.setInterceptFileChooserDialog", {"enabled": True})

    res = call("Runtime.evaluate", {"expression": cell_js(args.cell_index), "returnByValue": True})
    click_result = res.get("result", {}).get("result", {}).get("value")
    print("run:", click_result)

    if args.file:
        deadline = time.time() + args.timeout
        handled = False
        ws.settimeout(3)
        while time.time() < deadline:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                continue
            if msg.get("method") == "Page.fileChooserOpened":
                mode = msg["params"].get("mode", "selectSingle")
                call("Page.handleFileChooser", {"files": [args.file], "mode": mode})
                print(f"file chooser handled ({mode}): {args.file}")
                handled = True
                break
        if not handled:
            print(f"no file chooser event within {args.timeout}s")

    time.sleep(3)
    out = call(
        "Runtime.evaluate",
        {
            "expression": (
                "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
                "const c = cells[%d]; if (!c) return ''; "
                "const outs = [...c.querySelectorAll('.output_area pre, .codecell-output pre, .output pre')]"
                ".map(p => p.innerText || p.textContent || ''); return outs.join('\\n---\\n').slice(0, 1500); })()"
                % args.cell_index
            ),
            "returnByValue": True,
        },
    )
    val = out.get("result", {}).get("result", {}).get("value", "")
    print("=== cell output (first 1500 chars) ===")
    print(val or "(no output yet)")
    ws.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
