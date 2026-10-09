# Price Watcher

Track prices over time — groceries, gas, anything — with local history,
trend stats, buy-now alerts, CSV import/export, and a family-friendly web
dashboard. Zero dependencies (Python stdlib only).

## Quick start

```bash
python3 main.py add Milk Groceries --unit gallon
python3 main.py record Milk 4.49
python3 main.py record Milk 3.99
python3 main.py watch Milk 4.00      # alert when it drops below $4
python3 main.py check                # "Good time to buy" list
python3 main.py stats                # savings + trends overview
python3 main.py web                  # launch the dashboard at :8765
```

## Commands

| Command | What it does |
|---|---|
| `add <name> [category] [-u unit] [-n notes]` | watch a new item |
| `remove <name>` | stop watching |
| `record <name> <price> [--date YYYY-MM-DD]` | log a price |
| `list [-c category]` | all items: latest, best, trend, alert |
| `trend <name> [--last N]` | price history |
| `watch <name> <target>` / `watch <name>` | set / clear a buy-now alert |
| `check` | items currently at/below their alert price |
| `stats [name]` | per-item or overall savings & trends |
| `export [--out file.csv]` | CSV snapshot |
| `import file.csv` | restore from CSV |
| `web [--port 8765]` | local dashboard |

## Data

- Store: `data/prices.json` (single file — back it up, share it, or move it)
- Point it elsewhere with `PRICE_WATCHER_DATA=/path` or `--data /path`
- History capped at 500 entries per item

## Web dashboard

`python3 main.py web` opens a dark dashboard showing item cards with a
mini price chart, trend tags, and "good time to buy" callouts. Data is
read live from the same JSON store the CLI uses.

## Status

Built out from the batch-1 scaffold (leader-requested idea). The core
(`price_watcher.py`) is importable, so Jarvis or the other price apps can
drive it programmatically later.
