#!/usr/bin/env python3
"""quick-latency-stats.py — pick-latency stats from the combined puzzle corpus."""
import json, statistics, sys
path = sys.argv[1] if len(sys.argv) > 1 else "training/cloud/puzzle-r30/episodes.jsonl"
rows = [json.loads(l) for l in open(path) if l.strip()]
corr = [r["latency_s"] for r in rows if r.get("correct")]
wrong = [r["latency_s"] for r in rows if not r.get("correct")]
allt = [r["latency_s"] for r in rows]

def s(x):
    if not x:
        return "none"
    xs = sorted(x)
    return (f"n={len(x)} mean={statistics.mean(x):.1f}s med={statistics.median(x):.1f}s "
            f"p90={xs[int(len(x) * 0.9)]:.1f}s")

print("total picks:", len(rows))
print("CORRECT picks :", s(corr))
print("WRONG picks   :", s(wrong))
print("ALL           :", s(allt))
by = {}
for r in rows:
    by.setdefault(r.get("tier", "?"), []).append(r)
for t, rs in sorted(by.items()):
    lt = [r["latency_s"] for r in rs]
    acc = 100 * sum(r["correct"] for r in rs) / len(rs)
    print(f"{t:8s} n={len(rs):3d}  mean={statistics.mean(lt):6.1f}s  "
          f"median={statistics.median(lt):5.1f}s  acc={acc:.0f}%")