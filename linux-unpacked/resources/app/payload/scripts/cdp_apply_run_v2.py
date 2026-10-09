#!/usr/bin/env python3
"""Apply wrapper v2 to cell 12 via Monaco setValue, run the cell, verify it
enters 'running' state, and report the stream + outputframe content."""
import json
import sys
import time
import urllib.request

import websocket

NEW_CODE = r'''exec("import os, subprocess, sys, time, threading\nos.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '120'\nos.environ['HF_HUB_ETAG_TIMEOUT'] = '60'\nos.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'\nprint('wrapper: starting trainer, line-relay output + GPU heartbeat', flush=True)\ncmd = ['python', '-u', '/content/train_round1.py', '--dataset', '/content/dataset/round6-bible-10h.jsonl', '--out-dir', '/content/out', '--rounds', '1', '--start-round', '6', '--lr', str(LR), '--epochs', str(EPOCHS), '--max-seq-length', '2048']\nprint('CMD ' + ' '.join(cmd), flush=True)\ndef gpu():\n    while True:\n        time.sleep(60)\n        try:\n            r = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader'], capture_output=True, text=True, timeout=20)\n            print('GPU> ' + (r.stdout or '').strip()[:70], flush=True)\n        except Exception as e:\n            print('GPU> ERR ' + repr(e)[:70], flush=True)\nthreading.Thread(target=gpu, daemon=True).start()\np = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True)\nfor line in p.stdout:\n    print(line.rstrip(), flush=True)\nrc = p.wait()\nprint('trainer exited rc ' + str(rc), flush=True)")'''

EXPECT = 'line-relay output + GPU heartbeat'

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
mid = [0]


def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg


def evaljs(expr):
    msg = call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    r = msg.get("result", {})
    if r.get("exceptionDetails"):
        return "JSERR: " + json.dumps(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200]
    return r.get("result", {}).get("value")


# 1) Set the value via Monaco
setjs = (
    "(() => { const m = monaco; if (!m || !m.editor) return 'no monaco'; "
    "const eds = m.editor.getEditors(); "
    "const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const target = eds.find(e => { const d = e.getDomNode(); return d && d.closest('.cell.code.notebook-cell') === cells[5]; }); "
    "if (!target) return 'no target editor'; "
    "target.setValue(" + json.dumps(NEW_CODE) + "); "
    "return 'set ok len ' + target.getValue().length; })()"
)
print("setValue:", evaljs(setjs))
time.sleep(1.0)

# 2) Verify the model holds our code
cur = evaljs(
    "(() => { const m = monaco; const eds = m.editor.getEditors(); "
    "const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const t = eds.find(e => { const d = e.getDomNode(); return d && d.closest('.cell.code.notebook-cell') === cells[5]; }); "
    "return t ? t.getValue() : 'none'; })()"
) or ""
print("has EXPECT:", EXPECT in cur, "| len:", len(cur))

# 3) Click the run button for notebook cell 12
clickjs = (
    "(() => { const runs = [...document.querySelectorAll('colab-run-button')]; "
    "const run = runs[12]; if (!run) return 'no run btn 12 (' + runs.length + ' total)'; "
    "const root = run.shadowRoot || run; "
    "const btn = root.querySelector('button[aria-label=\"Run cell\"]') || root.querySelector('button'); "
    "if (!btn) return 'no button in shadow'; "
    "btn.click(); return 'clicked'; })()"
)
print("run click:", evaljs(clickjs))
time.sleep(6)

# 4) Verify the cell entered 'running'
state = evaljs(
    "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "return cells[5] ? cells[5].className.slice(0, 90) : 'no cell'; })()"
)
print("cell state after 6s:", state)

# 5) Dump stream + outputframes
stream = evaljs(
    "(() => { const cells = [...document.querySelectorAll('.cell.code.notebook-cell')]; "
    "const c = cells[5]; if (!c) return 'no cell'; "
    "const pres = [...c.querySelectorAll('.stream pre, .output pre, .output_text pre')]; "
    "const texts = pres.map(p => (p.innerText || '')); "
    "const t = texts.join('\\n---\\n'); "
    "return JSON.stringify({ len: t.length, tail: t.slice(-700) }); })()"
)
print("cell stream:", stream)

frame_text = evaljs(
    "(() => { const all = [...document.querySelectorAll('iframe')]; "
    "const out = []; "
    "for (const f of all) { "
    "  const t = f.contentDocument ? f.contentDocument.body.innerText : ''; "
    "  if (t && t.length > 10) out.push({ src: (f.src || '').slice(0, 60), len: t.length, tail: t.slice(-150) }); "
    "} "
    "return JSON.stringify(out); })()"
)
print("frames:", frame_text)
ws.close()
