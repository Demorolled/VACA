#!/usr/bin/env python3
"""Kaggle round-6 loss curve watcher (CDP-driven).

Polls the round-6 kernel page (browser on port 9222), extracts the full loss
checkpoint history + progress bar, and:
  1. Appends any NEW checkpoints to data/round6-loss-curve.json (deduped)
  2. At >= TARGET_PCT (default 95): writes data/round6-95pct-snapshot.json
  3. On completion: writes data/round6-final-snapshot.json with final stats

Run (background):
    python3 scripts/kaggle-round6-loss-watch.py > data/round6-loss-watch.log 2>&1 &
"""
import json
import os
import re
import sys
import time
import urllib.request
import websocket

PORT = 9222
URL_PREFIX = "https://www.kaggle.com/code/stevenawoods/vaca-qlora-round6"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURVE = os.path.join(ROOT, "data", "round6-loss-curve.json")
SNAP95 = os.path.join(ROOT, "data", "round6-95pct-snapshot.json")
FINAL = os.path.join(ROOT, "data", "round6-final-snapshot.json")
TARGET_PCT = float(os.environ.get("TARGET_PCT", "95"))
POLL_S = int(os.environ.get("POLL_S", "300"))

LOSS_RE = re.compile(
    r"\{'loss': '([0-9.]+)', 'grad_norm': '([0-9.]+)', "
    r"'learning_rate': '([0-9.e-]+)', 'epoch': '([0-9.]+)'\}"
)
BAR_RE = re.compile(r"(\d+)%\|.*\| *(\d+)/(\d+) \[([0-9:]+)<([0-9:]+)[^\]]*\]")


def get_page_ws():
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
    page = next(
        (t for t in tabs if t.get("type") == "page" and t.get("url", "").startswith(URL_PREFIX)),
        None,
    )
    if page is None:
        page = next((t for t in tabs if t.get("type") == "page"), None)
    if page is None:
        raise RuntimeError("no page tab")
    return page["webSocketDebuggerUrl"], page.get("url", "")


def rpc(ws, method, params=None, mid=[0]):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg


def read_state():
    ws_url, url = get_page_ws()
    ws = websocket.create_connection(ws_url, timeout=20)
    try:
        js = """(() => {
          const body = document.body.innerText||'';
          const rows = [];
          const rex = /\\{'loss': '([0-9.]+)', 'grad_norm': '([0-9.]+)', 'learning_rate': '([0-9.e-]+)', 'epoch': '([0-9.]+)'\\}/g;
          let m;
          while ((m = rex.exec(body)) !== null) rows.push({loss: parseFloat(m[1]), grad: parseFloat(m[2]), lr: parseFloat(m[3]), epoch: parseFloat(m[4])});
          const bars = [];
          const bre = /(\\d+)%\\|.*\\| *(\\d+)\\/(\\d+) \\[([0-9:]+)<([0-9:]+)[^\\]]*\\]/g;
          let b;
          while ((b = bre.exec(body)) !== null) bars.push({pct: parseInt(b[1]), step: parseInt(b[2]), total: parseInt(b[3]), elapsed: b[4], eta: b[5]});
          const runSec = /Running for ([0-9.]+)s/.exec(body);
          const comp = /Output\\n\\n([0-9.]+ [KMG]?B)/.exec(body);
          return JSON.stringify({
            rows,
            lastBar: bars.length ? bars[bars.length-1] : null,
            runSec: runSec ? runSec[1] : null,
            outputSize: comp ? comp[1] : null,
          });
        })()"""
        r = rpc(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True})
        val = r.get("result", {}).get("result", {}).get("value", "{}")
        return json.loads(val), url
    finally:
        ws.close()


def dedupe_curve(existing, rows):
    """Merge rows into the existing curve, deduped by (epoch, loss)."""
    seen = set()
    out = list(existing)
    for x in out:
        seen.add((round(x["epoch"], 4), round(x["loss"], 4)))
    added = 0
    for x in rows:
        key = (round(x["epoch"], 4), round(x["loss"], 4))
        if key not in seen:
            seen.add(key)
            out.append(x)
            added += 1
    out.sort(key=lambda r: r["epoch"])
    return out, added


def stats(rows):
    if not rows:
        return {}
    losses = [r["loss"] for r in rows]
    grads = [r["grad"] for r in rows]
    return {
        "n_checkpoints": len(rows),
        "first_loss": losses[0],
        "min_loss": min(losses),
        "last_loss": losses[-1],
        "loss_drop_pct": round(100 * (1 - losses[-1] / losses[0]), 1) if losses[0] else 0,
        "grad_min": min(grads),
        "grad_max": max(grads),
    }


def main():
    curve = []
    if os.path.exists(CURVE):
        try:
            curve = json.load(open(CURVE))
        except Exception:
            curve = []
    os.makedirs(os.path.dirname(CURVE), exist_ok=True)

    fired_95 = os.path.exists(SNAP95)
    done = False
    loops = 0
    max_loops = int(os.environ.get("MAX_LOOPS", "60"))  # ~5h at 5 min

    while loops < max_loops:
        loops += 1
        try:
            state, url = read_state()
        except Exception as e:
            print(f"[{time.ctime()}] read error: {e}", flush=True)
            time.sleep(POLL_S)
            continue

        rows = state.get("rows", [])
        bar = state.get("lastBar")
        curve, added = dedupe_curve(curve, rows)
        json.dump(curve, open(CURVE, "w"), indent=2)

        pct = bar["pct"] if bar else 0
        st = stats(curve)
        print(
            f"[{time.ctime()}] pct={pct}% step={bar['step'] if bar else '?'}/"
            f"{bar['total'] if bar else '?'} eta={bar['eta'] if bar else '?'} "
            f"checkpoints={len(curve)} (+{added}) last_loss={st.get('last_loss')}",
            flush=True,
        )

        # 95% snapshot (fire once)
        if not fired_95 and pct >= TARGET_PCT:
            snap = {"captured_at": time.ctime(), "pct": pct, "bar": bar,
                    "run_seconds": state.get("runSec"), "curve": list(curve),
                    "stats": st}
            json.dump(snap, open(SNAP95, "w"), indent=2)
            fired_95 = True
            print(f"[{time.ctime()}] ✅ {TARGET_PCT}% snapshot saved to {SNAP95}", flush=True)

        # Completion: output size present and no running bar
        if state.get("outputSize") and (not bar or bar["pct"] >= 99):
            snap = {"captured_at": time.ctime(), "final": True, "bar": bar,
                    "run_seconds": state.get("runSec"),
                    "output_size": state.get("outputSize"), "curve": list(curve),
                    "stats": st}
            json.dump(snap, open(FINAL, "w"), indent=2)
            print(f"[{time.ctime()}] 🏁 FINAL snapshot saved to {FINAL}: {json.dumps(st)}", flush=True)
            done = True
            break

        time.sleep(POLL_S)

    if not done:
        print(f"[{time.ctime()}] watcher exited after {loops} loops without completion", flush=True)


if __name__ == "__main__":
    main()
