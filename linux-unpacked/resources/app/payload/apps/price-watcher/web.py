"""
Price Watcher — local web dashboard (stdlib only).

Serves a dark, family-friendly dashboard at http://localhost:<port>
showing every watched item with latest/best price, a mini price chart,
trend direction, and "good time to buy" callouts. Data is read live from
the same JSON store the CLI uses.

Usage:
  python3 web.py [--port 8765] [--data <dir>]
  python3 main.py web [--port 8765]
"""

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from price_watcher import Store, DEFAULT_DATA_DIR

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price Watcher</title>
<style>
  :root { --bg:#0d1117; --surface:#161b22; --border:#30363d; --text:#e6edf3;
          --dim:#8b949e; --accent:#58a6ff; --good:#2ea043; --bad:#f85149; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text);
         margin: 0; padding: 2rem 1rem; }
  .wrap { max-width: 900px; margin: 0 auto; }
  header { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }
  h1 { font-size: 1.5rem; margin: 0; }
  .muted { color: var(--dim); font-size: .9rem; }
  .summary { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
          padding: .9rem 1.1rem; flex: 1; min-width: 150px; }
  .card .k { color: var(--dim); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
  .card .v { font-size: 1.3rem; font-weight: 700; margin-top: .2rem; }
  .deal { color: var(--good); }
  .items { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: .8rem; }
  .item { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: .9rem 1rem; }
  .item h3 { margin: 0 0 .3rem; font-size: 1rem; }
  .cat { color: var(--dim); font-size: .75rem; }
  .prices { display: flex; justify-content: space-between; margin: .5rem 0; font-size: .9rem; }
  .latest { font-size: 1.25rem; font-weight: 700; color: var(--accent); }
  .bars { display: flex; align-items: flex-end; gap: 3px; height: 44px; margin-top: .4rem; }
  .bar { flex: 1; background: var(--accent); border-radius: 2px 2px 0 0; opacity: .75; }
  .bar.latest { background: var(--good); opacity: 1; }
  .alert-on { border-color: var(--good); }
  .alert-hit { border-color: var(--good); background: #0f2317; }
  .tag { font-size: .7rem; border-radius: 99px; padding: .15rem .5rem; }
  .tag.rising { background: #3a1d1d; color: var(--bad); }
  .tag.falling { background: #1a3a22; color: var(--good); }
  .tag.flat { background: #22272e; color: var(--dim); }
  button { background: var(--surface); color: var(--text); border: 1px solid var(--border);
           border-radius: 8px; padding: .4rem .8rem; cursor: pointer; }
  button:hover { border-color: var(--accent); }
  .empty { color: var(--dim); text-align: center; margin-top: 3rem; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><h1>📈 Price Watcher</h1><div class="muted" id="updated">—</div></div>
    <button onclick="load()">↻ Refresh</button>
  </header>
  <div class="summary" id="summary"></div>
  <div class="items" id="items"></div>
  <div class="empty" id="empty" hidden>Nothing being watched yet — add items with the CLI:
    <code>python3 main.py add Milk Groceries</code></div>
</div>
<script>
async function load() {
  const r = await fetch('/api/data');
  const data = await r.json();
  const items = data.items || [];
  document.getElementById('updated').textContent = 'Updated ' + new Date(data.updated).toLocaleTimeString();
  const good = items.filter(i => i.buyNow);
  document.getElementById('summary').innerHTML =
    card('Watching', items.length) +
    card('Good time to buy', good.length, good.length ? 'deal' : '') +
    card('Avg. saving vs best', '$' + (data.avgSavings || 0).toFixed(2), 'deal');
  const box = document.getElementById('items');
  box.innerHTML = items.map(renderItem).join('');
  document.getElementById('empty').hidden = items.length > 0;
}
function card(k, v, cls) { return '<div class="card"><div class="k">' + k + '</div><div class="v ' + (cls||'') + '">' + v + '</div></div>'; }
function renderItem(i) {
  const bars = i.recent.map((p, idx) =>
    '<div class="bar' + (idx === i.recent.length - 1 ? ' latest' : '') + '" style="height:' +
    Math.max(6, Math.round((p / i.maxPrice) * 100)) + '%" title="' + i.history[idx][0] + ': $' + p.toFixed(2) + '"></div>').join('');
  const cls = i.buyNow ? 'item alert-hit' : (i.alert ? 'item alert-on' : 'item');
  const tag = '<span class="tag ' + i.trend + '">' + ({falling:'⬇ falling', rising:'⬆ rising', flat:'→ flat'})[i.trend] + '</span>';
  const alert = i.alert ? ' · alert ≤$' + i.alert.toFixed(2) : '';
  return '<div class="' + cls + '"><h3>' + i.name + ' ' + tag + '</h3>' +
    '<div class="cat">' + (i.category || 'uncategorized') + alert + (i.unit ? ' / ' + i.unit : '') + '</div>' +
    '<div class="prices"><span class="latest">$' + i.latest.toFixed(2) + '</span>' +
    '<span class="muted">best $' + i.best.toFixed(2) + '</span></div>' +
    '<div class="bars">' + bars + '</div></div>';
}
load();
</script>
</body>
</html>
"""


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep the console quiet

        def _json(self, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/data":
                items = []
                for s in store.all_stats():
                    history = store.history(s["name"])
                    recent = [p for _, p in history][-12:]
                    items.append({
                        "name": s["name"], "category": s["category"],
                        "unit": s["unit"], "latest": s["latest"], "best": s["best"],
                        "trend": s["trend"], "alert": s["alert"],
                        "buyNow": s["alert"] is not None and s["latest"] <= s["alert"],
                        "history": history[-12:], "recent": recent,
                        "maxPrice": max(recent) if recent else 1,
                    })
                avg_savings = sum(s["savings"] for s in store.all_stats() if s["savings"] < 0)
                self._json({"updated": __import__("datetime").datetime.now().isoformat(),
                            "items": items, "avgSavings": -avg_savings})
            else:
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

    return Handler


def serve(store: Store, port: int = 8765, open_browser: bool = True) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))
    url = f"http://127.0.0.1:{port}"
    print(f"📈 Price Watcher dashboard at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Price Watcher web dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    data_dir = Path(args.data) if args.data else DEFAULT_DATA_DIR
    return serve(Store(data_dir=data_dir), port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    import sys
    sys.exit(main())
