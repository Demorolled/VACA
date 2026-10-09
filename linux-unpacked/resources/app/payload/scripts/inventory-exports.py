#!/usr/bin/env python3
"""Print an inventory of chunkable exports: node count, size, multi-file, purpose spread."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent))

from puzzle_trainer import Library

ROOT = Path(__file__).resolve().parent.parent
lib = Library(ROOT / "backend" / "exports", max_apps=None)

rows = []
for name, a in lib.apps.items():
    n = len(a["nodes"])
    html = ROOT / "backend" / "exports" / name / "index.html"
    size = html.stat().st_size if html.exists() else 0
    multi = (ROOT / "backend" / "exports" / name / "client").exists() or \
            (ROOT / "backend" / "exports" / name / "server").exists()
    req = (a["request"] or "")[:60]
    rows.append((n, size, multi, name, req))
rows.sort(key=lambda r: (-r[0], -r[1]))

print("total chunkable: %d" % len(rows))
print("%5s %8s %5s  %-50s | %s" % ("nodes", "size", "multi", "app", "request"))
for n, s, m, name, req in rows:
    print("%5d %8d %5s  %-50s | %s" % (n, s, str(m), name[:50], req))

c = Counter()
for a in lib.apps.values():
    for nd in a["nodes"]:
        c[nd["purpose"]] += 1
print("purposes:", dict(c))
