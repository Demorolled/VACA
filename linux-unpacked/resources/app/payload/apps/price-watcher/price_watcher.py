"""
Price Watcher core — track prices over time (groceries, gas, anything).

A small, dependency-free library behind the CLI and web dashboard:
  - JSON-backed store (one file, easy to back up / share)
  - Per-item price history with date stamps
  - "Buy now" alerts when the latest price drops below a target
  - Stats: best / worst / average / trend per item
  - CSV export & import (so you can move between apps or load history)
"""

import csv
import io
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
MAX_HISTORY = 500  # keep at most this many price points per item


def normalize_name(name: str) -> str:
    """Canonical item key: trimmed, whitespace-collapsed, title case."""
    return " ".join((name or "").split()).title()


class Store:
    """JSON-backed price history store."""

    def __init__(self, data_dir: Optional[Path | str] = None):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.path = self.data_dir / "prices.json"
        self._data = self._load()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        default = {"items": {}}
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for k, v in default.items():
                    data.setdefault(k, v)
                return data
        except Exception as e:
            logger.warning(f"Could not read store {self.path}: {e}")
        return default

    def _save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # ── Item helpers ───────────────────────────────────────────────────

    def _key(self, name: str) -> str:
        return normalize_name(name)

    def item(self, name: str) -> Optional[dict]:
        return self._data["items"].get(self._key(name))

    def names(self) -> list[str]:
        return sorted(self._data["items"].keys(), key=str.lower)

    # ── CRUD ───────────────────────────────────────────────────────────

    def add(self, name: str, category: str = "", unit: str = "",
            notes: str = "") -> tuple[bool, str]:
        key = self._key(name)
        if not key:
            return False, "Item name can't be empty."
        items = self._data["items"]
        if key in items:
            return False, f"'{key}' is already being watched (latest: {self.latest_price(key)})."
        items[key] = {"category": category.strip(), "unit": unit.strip(),
                      "history": [], "alert_max": None, "notes": notes.strip()}
        self._save()
        parts = [f"'{key}' added to the watch list"]
        if category:
            parts.append(f"category: {category.strip()}")
        if unit:
            parts.append(f"unit: {unit.strip()}")
        return True, ", ".join(parts) + "."

    def remove(self, name: str) -> tuple[bool, str]:
        key = self._key(name)
        if key not in self._data["items"]:
            return False, f"'{key}' isn't being watched."
        del self._data["items"][key]
        self._save()
        return True, f"'{key}' removed."

    def record(self, name: str, price: float, when: Optional[str] = None) -> tuple[bool, str]:
        key = self._key(name)
        item = self._data["items"].get(key)
        if item is None:
            return False, f"'{key}' isn't being watched yet — add it first (add {name})."
        try:
            price = round(float(price), 2)
        except (TypeError, ValueError):
            return False, f"'{price}' isn't a valid price."
        if price <= 0:
            return False, "Price must be greater than zero."
        day = when or date.today().isoformat()
        history = item.setdefault("history", [])
        history.append([day, price])
        if len(history) > MAX_HISTORY:
            del history[: len(history) - MAX_HISTORY]
        self._save()
        return True, f"Recorded {key}: ${price:.2f} on {day}."

    def history(self, name: str) -> list[tuple[str, float]]:
        item = self.item(name)
        if not item:
            return []
        return [(d, p) for d, p in item.get("history", [])]

    def latest_price(self, name: str) -> Optional[float]:
        history = self.history(name)
        if not history:
            return None
        # Most recent by date — a backdated entry must not become "current".
        return max(history, key=lambda h: h[0])[1]

    # ── Alerts ─────────────────────────────────────────────────────────

    def set_alert(self, name: str, max_price: float) -> tuple[bool, str]:
        key = self._key(name)
        item = self._data["items"].get(key)
        if item is None:
            return False, f"'{key}' isn't being watched — add it first."
        try:
            max_price = round(float(max_price), 2)
        except (TypeError, ValueError):
            return False, f"'{max_price}' isn't a valid target price."
        item["alert_max"] = max_price
        self._save()
        return True, f"Alert set: I'll flag {key} when it drops below ${max_price:.2f}."

    def clear_alert(self, name: str) -> tuple[bool, str]:
        key = self._key(name)
        item = self._data["items"].get(key)
        if item is None:
            return False, f"'{key}' isn't being watched."
        item["alert_max"] = None
        self._save()
        return True, f"Alert cleared for {key}."

    def check_alerts(self) -> list[dict]:
        """Items whose latest price is at or below their alert target."""
        hits = []
        for name, item in self._data["items"].items():
            alert = item.get("alert_max")
            history = item.get("history", [])
            if alert and history:
                latest = history[-1][1]
                if latest <= alert:
                    hits.append({"name": name, "latest": latest,
                                 "alert": alert, "category": item.get("category", "")})
        return sorted(hits, key=lambda h: h["name"].lower())

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self, name: str) -> Optional[dict]:
        history = self.history(name)
        if not history:
            return None
        prices = [p for _, p in history]
        latest = prices[-1]
        best = min(prices)
        worst = max(prices)
        avg = sum(prices) / len(prices)
        prev = prices[-6:-1]
        if prev:
            prev_avg = sum(prev) / len(prev)
            if latest < prev_avg * 0.98:
                trend = "falling"
            elif latest > prev_avg * 1.02:
                trend = "rising"
            else:
                trend = "flat"
        else:
            trend = "flat"
        item = self.item(name)
        return {
            "name": name,
            "latest": latest,
            "best": best,
            "worst": worst,
            "average": avg,
            "count": len(history),
            "trend": trend,
            "alert": item.get("alert_max") if item else None,
            "unit": item.get("unit", "") if item else "",
            "category": item.get("category", "") if item else "",
            "savings": round(best - latest, 2),  # negative = above your best price
        }

    def all_stats(self) -> list[dict]:
        return [self.stats(name) for name in self.names() if self.stats(name)]

    # ── CSV ────────────────────────────────────────────────────────────

    CSV_HEADER = ["item", "category", "unit", "alert_max", "latest_price", "date"]

    def export_csv(self) -> str:
        """CSV snapshot: item, category, unit, alert, latest price + date."""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.CSV_HEADER)
        writer.writeheader()
        for name in self.names():
            item = self.item(name)
            history = item.get("history", [])
            latest = history[-1] if history else None
            writer.writerow({
                "item": name,
                "category": item.get("category", ""),
                "unit": item.get("unit", ""),
                "alert_max": item.get("alert_max") or "",
                "latest_price": latest[1] if latest else "",
                "date": latest[0] if latest else "",
            })
        return buf.getvalue().strip()

    def import_csv(self, text: str) -> tuple[int, str]:
        """Import a CSV (same header as export). Returns (added, message)."""
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return 0, "Empty CSV."
        added = 0
        for row in reader:
            name = (row.get("item") or "").strip()
            if not name:
                continue
            category = (row.get("category") or "").strip()
            unit = (row.get("unit") or "").strip()
            is_new = self.item(name) is None
            ok, _ = self.add(name, category=category, unit=unit)
            if not ok and not is_new:
                # exists — update category/unit only (never clobber history)
                item = self.item(name)
                if category and not item.get("category"):
                    item["category"] = category
                if unit and not item.get("unit"):
                    item["unit"] = unit
            price = (row.get("latest_price") or "").strip()
            when = (row.get("date") or "").strip()
            if price and is_new:  # only seed history for new items
                try:
                    self.record(name, float(price), when=when or None)
                except (TypeError, ValueError):
                    pass
            alert = (row.get("alert_max") or "").strip()
            if alert:
                try:
                    self.set_alert(name, float(alert))
                except (TypeError, ValueError):
                    pass
            added += 1
        self._save()
        return added, f"Imported {added} item(s) from CSV."
