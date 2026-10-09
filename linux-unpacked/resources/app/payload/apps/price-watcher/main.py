#!/usr/bin/env python3
"""
Price Watcher — track prices over time (groceries, gas, anything).

A dependency-free CLI: record what things cost, watch trends, set buy-now
alerts, export/import CSV, and launch a local web dashboard.

Examples:
  python3 main.py add Milk Groceries
  python3 main.py record Milk 4.49
  python3 main.py watch Milk 4.00
  python3 main.py check
  python3 main.py stats
  python3 main.py export --out shopping.csv
  python3 main.py web

Set PRICE_WATCHER_DATA to keep the store somewhere else.
"""

import argparse
import os
import sys
from pathlib import Path

from price_watcher import Store, DEFAULT_DATA_DIR

TREND_ICON = {"falling": "⬇", "rising": "⬆", "flat": "→"}


def data_dir_from_args(args) -> Path:
    return Path(args.data) if getattr(args, "data", None) else DEFAULT_DATA_DIR


def cmd_add(store: Store, args) -> int:
    ok, msg = store.add(args.name, category=args.category or "",
                        unit=args.unit or "", notes=args.notes or "")
    print(msg)
    return 0 if ok else 1


def cmd_remove(store: Store, args) -> int:
    ok, msg = store.remove(args.name)
    print(msg)
    return 0 if ok else 1


def cmd_record(store: Store, args) -> int:
    ok, msg = store.record(args.name, args.price, when=args.date)
    print(msg)
    return 0 if ok else 1


def cmd_list(store: Store, args) -> int:
    stats = store.all_stats()
    if args.category:
        stats = [s for s in stats if s["category"].lower() == args.category.lower()]
    if not stats:
        print("Nothing being watched yet. Try: add Milk Groceries")
        return 0
    width = max(len(s["name"]) for s in stats) + 2
    print(f"{'ITEM'.ljust(width)}{'LATEST':>10}{'BEST':>10}{'TREND':>7}  ALERT")
    for s in stats:
        alert = f"${s['alert']:.2f}" if s["alert"] else "—"
        print(f"{s['name'].ljust(width)}"
              f"${s['latest']:>9.2f}"
              f"${s['best']:>9.2f}"
              f"{TREND_ICON[s['trend']]:>7}  {alert}")
    return 0


def cmd_trend(store: Store, args) -> int:
    history = store.history(args.name)
    if not history:
        print(f"No price history for '{args.name}'.")
        return 1
    last = history[-args.last:]
    print(f"Trend for {args.name}:")
    for day, price in last:
        marker = " ◀ latest" if (day, price) == history[-1] else ""
        print(f"  {day}  ${price:>8.2f}{marker}")
    return 0


def cmd_watch(store: Store, args) -> int:
    if args.max_price is None:
        ok, msg = store.clear_alert(args.name)
    else:
        ok, msg = store.set_alert(args.name, args.max_price)
    print(msg)
    return 0 if ok else 1


def cmd_check(store: Store, args) -> int:
    hits = store.check_alerts()
    if not hits:
        print("Nothing is below its alert price right now.")
        return 0
    print("Good time to buy:")
    for h in hits:
        cat = f" ({h['category']})" if h["category"] else ""
        print(f"  • {h['name']}{cat} — ${h['latest']:.2f} (alert: ≤${h['alert']:.2f})")
    return 0


def cmd_stats(store: Store, args) -> int:
    if args.name:
        s = store.stats(args.name)
        if not s:
            print(f"No prices for '{args.name}' yet.")
            return 1
        _print_stats(s)
        return 0
    stats = store.all_stats()
    if not stats:
        print("Nothing being watched yet.")
        return 0
    total_items = len(stats)
    total_savings = sum(s["savings"] for s in stats if s["savings"] < 0)
    below_best = sum(1 for s in stats if s["savings"] < 0)
    categories = {}
    for s in stats:
        cat = s["category"] or "other"
        categories[cat] = categories.get(cat, 0) + 1
    print(f"Watching {total_items} items across {len(categories)} categories.")
    if categories:
        print("  " + ", ".join(f"{c}: {n}" for c, n in sorted(categories.items())))
    print(f"{below_best} item(s) are above their best price"
          f" (potential saving ${-total_savings:.2f} if you wait for deals).")
    print("\nPer-item:")
    for s in stats:
        _print_stats(s)
    return 0


def _print_stats(s: dict) -> None:
    unit = f"/{s['unit']}" if s.get("unit") else ""
    alert = f", alert ≤${s['alert']:.2f}" if s.get("alert") else ""
    print(f"{s['name']}: latest ${s['latest']:.2f}{unit} · best ${s['best']:.2f} · "
          f"avg ${s['average']:.2f} · trend {TREND_ICON[s['trend']]} {s['trend']}"
          f" · {s['count']} entries{alert}")


def cmd_export(store: Store, args) -> int:
    csv_text = store.export_csv()
    if args.out:
        Path(args.out).write_text(csv_text + "\n", encoding="utf-8")
        print(f"Exported {len(store.names())} item(s) to {args.out}.")
    else:
        print(csv_text)
    return 0


def cmd_import(store: Store, args) -> int:
    try:
        text = Path(args.file).read_text(encoding="utf-8")
    except OSError as e:
        print(f"Couldn't read {args.file}: {e}")
        return 1
    added, msg = store.import_csv(text)
    print(msg)
    return 0


def cmd_web(store: Store, args) -> int:
    from web import serve
    return serve(store, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="price-watcher", description=__doc__.split("\n\n")[0])
    p.add_argument("--data", help="directory for the store (default: ./data or $PRICE_WATCHER_DATA)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("add", help="watch a new item")
    s.add_argument("name"); s.add_argument("category", nargs="?", default="")
    s.add_argument("-u", "--unit"); s.add_argument("-n", "--notes")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("remove", help="stop watching an item")
    s.add_argument("name"); s.set_defaults(func=cmd_remove)

    s = sub.add_parser("record", help="log today's price for an item")
    s.add_argument("name"); s.add_argument("price", type=float)
    s.add_argument("--date", help="override date (YYYY-MM-DD)")
    s.set_defaults(func=cmd_record)

    s = sub.add_parser("list", help="all items, latest + best price")
    s.add_argument("-c", "--category")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("trend", help="price history for an item")
    s.add_argument("name"); s.add_argument("--last", type=int, default=14)
    s.set_defaults(func=cmd_trend)

    s = sub.add_parser("watch", help="alert when price drops below target (no value = clear)")
    s.add_argument("name"); s.add_argument("max_price", type=float, nargs="?")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("check", help="items now below their alert price")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("stats", help="savings + trend stats (per item or overall)")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("export", help="CSV snapshot")
    s.add_argument("--out", help="write to file instead of stdout")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("import", help="import a CSV (same format as export)")
    s.add_argument("file"); s.set_defaults(func=cmd_import)

    s = sub.add_parser("web", help="launch the local dashboard")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_web)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_data = os.environ.get("PRICE_WATCHER_DATA")
    if env_data and not getattr(args, "data", None):
        args.data = env_data
    store = Store(data_dir=data_dir_from_args(args))
    return args.func(store, args)


if __name__ == "__main__":
    sys.exit(main())
