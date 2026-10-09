"""
Unit tests for Price Watcher (core + CLI). Uses a temp data dir — no
touching of the real store.
"""

import sys
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import pytest

from price_watcher import Store, normalize_name
from main import build_parser


@pytest.fixture
def store(tmp_path):
    return Store(data_dir=tmp_path / "pw")


# =============================================================================
#  Normalization
# =============================================================================

class TestNormalize:
    def test_title_and_collapse(self):
        assert normalize_name("  milk ") == "Milk"
        assert normalize_name("GROUND   BEEF") == "Ground Beef"


# =============================================================================
#  CRUD
# =============================================================================

class TestCRUD:
    def test_add_and_remove(self, store):
        ok, msg = store.add("milk", category="Dairy", unit="gallon")
        assert ok and "Milk" in msg
        assert store.item("MILK") is not None          # case-insensitive lookup
        ok, msg = store.remove("milk")
        assert ok and store.item("Milk") is None

    def test_add_duplicate(self, store):
        store.add("milk")
        ok, _ = store.add("Milk")
        assert not ok

    def test_record_requires_existing_item(self, store):
        ok, _ = store.record("nope", 1.0)
        assert not ok

    def test_record_validates_price(self, store):
        store.add("gas")
        assert store.record("gas", 0)[0] is False
        assert store.record("gas", -1)[0] is False
        assert store.record("gas", "abc")[0] is False

    def test_record_appends_history(self, store):
        from datetime import date
        store.add("gas")
        store.record("gas", 3.49)
        store.record("gas", 3.39, when="2026-08-01")
        history = store.history("gas")
        assert len(history) == 2
        assert history[0] == (date.today().isoformat(), 3.49)
        assert history[1] == ("2026-08-01", 3.39)
        assert store.latest_price("gas") == 3.49

    def test_history_capped(self, store, tmp_path):
        store.add("x")
        for i in range(600):
            store.record("x", 1.0 + i / 100)
        assert len(store.history("x")) == 500


# =============================================================================
#  Alerts
# =============================================================================

class TestAlerts:
    def test_set_and_clear(self, store):
        store.add("milk")
        store.set_alert("milk", 4.0)
        assert store.item("milk")["alert_max"] == 4.0
        store.clear_alert("milk")
        assert store.item("milk")["alert_max"] is None

    def test_check_hits(self, store):
        store.add("milk")
        store.set_alert("milk", 4.0)
        store.record("milk", 3.99)
        store.add("gas")
        store.set_alert("gas", 3.0)
        store.record("gas", 3.20)
        hits = store.check_alerts()
        assert [h["name"] for h in hits] == ["Milk"]


# =============================================================================
#  Stats
# =============================================================================

class TestStats:
    def test_stats_fields(self, store):
        store.add("gas")
        for p in (3.49, 3.39, 3.29, 3.19):
            store.record("gas", p)
        s = store.stats("gas")
        assert s["latest"] == 3.19
        assert s["best"] == 3.19
        assert s["worst"] == 3.49
        assert s["count"] == 4
        assert s["trend"] == "falling"
        assert s["savings"] == 0.0  # at best price

    def test_stats_none_when_no_history(self, store):
        store.add("gas")
        assert store.stats("gas") is None

    def test_trend_rising(self, store):
        store.add("gas")
        for p in (3.0, 3.1, 3.2, 3.3):
            store.record("gas", p)
        assert store.stats("gas")["trend"] == "rising"


# =============================================================================
#  CSV
# =============================================================================

class TestCSV:
    def test_export_import_roundtrip(self, store, tmp_path):
        store.add("milk", category="Dairy", unit="gallon")
        store.record("milk", 4.49)
        store.set_alert("milk", 4.0)
        csv_text = store.export_csv()
        assert "Milk" in csv_text and "Dairy" in csv_text

        other = Store(data_dir=tmp_path / "pw2")
        added, msg = other.import_csv(csv_text)
        assert added == 1
        assert other.item("Milk")["category"] == "Dairy"
        assert other.latest_price("Milk") == 4.49
        assert other.item("Milk")["alert_max"] == 4.0

    def test_import_does_not_clobber_existing_history(self, store):
        store.add("milk")
        store.record("milk", 3.0)
        csv_text = "item,category,unit,alert_max,latest_price,date\nmilk,Dairy,,,5.00,\n"
        store.import_csv(csv_text)
        assert store.latest_price("Milk") == 3.0   # history preserved


# =============================================================================
#  CLI (through the parser)
# =============================================================================

class TestCLI:
    def test_add_record_list(self, tmp_path):
        env = {"PRICE_WATCHER_DATA": str(tmp_path / "cli")}
        run = lambda *a: subprocess.run(
            [sys.executable, str(APP_DIR / "main.py"), *a],
            capture_output=True, text=True, env={**__import__("os").environ, **env})
        r1 = run("add", "Milk", "Groceries")
        assert r1.returncode == 0 and "Milk" in r1.stdout
        r2 = run("record", "Milk", "4.49")
        assert r2.returncode == 0 and "$4.49" in r2.stdout
        r3 = run("list")
        assert "Milk" in r3.stdout and "4.49" in r3.stdout
        r4 = run("record", "Milk", "0")
        assert r4.returncode == 1

    def test_parser_subcommands(self):
        parser = build_parser()
        for argv in (["add", "x"], ["record", "x", "1"], ["list"], ["stats"],
                     ["export"], ["web"]):
            args = parser.parse_args(argv)
            assert callable(args.func)
