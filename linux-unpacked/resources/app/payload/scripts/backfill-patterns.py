#!/usr/bin/env python3
"""
backfill-patterns.py — grow VACA's knowledge bank from every tsc-clean export.

The training captures (verified-generations.jsonl, repair-pairs, orpo-pairs) are
the "right and wrongs" — SFT/ORPO rows. This backfill feeds the OTHER store:
backend/knowledge/patterns.json (the "how to build apps" memory injected into
future builds via internalKnowledge). Since the store froze at 26 on Aug 15 while
every capture session ran (fixed in VACA_CHANGE_LIST #63), this folds the
accumulated tsc-clean exports back in.

Walks backend/exports/*, reads each `_training.json` sidecar, and for exports
whose sidecar recorded tscErrors == 0 learns one pattern per .ts/.tsx file plus
the full-app architecture pattern — via the LIVE /api/knowledge/learn route so
the exact same gated funnel (kill switch + isQualityCode) applies. Skips exports
already learned (architecture title present in the store).

Usage:
  python3 scripts/backfill-patterns.py            # all clean exports
  python3 scripts/backfill-patterns.py --limit 20 # first 20 (dry-run-ish)
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3001"
ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "backend" / "exports"


def api(method, path, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except Exception as e:
        return 0, {"error": str(e)}


def store_titles():
    st, d = api("GET", "/api/knowledge/", None)
    if st != 200:
        print(f"⚠ cannot read store (status={st}) — {str(d)[:120]}")
        return set()
    return set(p.get("title", "") for p in (d or {}).get("patterns", []))


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    existing = store_titles()
    print(f"store: {len(existing)} patterns before backfill")
    processed = learned_total = skipped = 0
    dirs = sorted(d for d in EXPORTS.iterdir() if d.is_dir())
    for d in dirs:
        if limit and processed >= limit:
            break
        sidecar_p = d / "_training.json"
        if not sidecar_p.exists():
            continue
        try:
            sidecar = json.loads(sidecar_p.read_text())
        except Exception:
            continue
        # Only tsc-clean exports — broken output never enters the knowledge bank.
        if sidecar.get("tscErrors", 0) > 0:
            skipped += 1
            continue
        request = sidecar.get("request") or d.name
        if f"{request} - Full architecture" in existing:
            skipped += 1
            continue  # already learned (idempotent re-runs)

        files = []
        for rel in sidecar.get("files", []):
            if not isinstance(rel, str) or not rel.endswith((".ts", ".tsx")):
                continue
            fp = d / rel
            if not fp.exists():
                continue
            code = fp.read_text()
            if len(code.strip()) < 80:
                continue
            files.append({"path": rel, "content": code, "language": "typescript"})
        if not files:
            skipped += 1
            continue

        # Same synthetic one-node-per-file project shape the write path builds
        # (learningEngine.learnFromFiles) — but posted to the live route so the
        # funnel applies unchanged.
        nodes = []
        for i, f in enumerate(files):
            label = Path(f["path"]).stem
            nodes.append({
                "id": f"file_{i}",
                "type": "logic",
                "position": {"x": 0, "y": i * 80},
                "data": {"label": label, "description": f"Generated file {f['path']}",
                         "status": "valid", "language": "typescript",
                         "generatedCode": f["content"]},
            })
        project = {
            "id": f"backfill_{time.time_ns()}",
            "name": request,
            "targetOS": "linux",
            "nodes": nodes,
            "edges": [],
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        generated_code = "\n\n".join(f["content"] for f in files)
        st, res = api("POST", "/api/knowledge/learn",
                      {"project": project, "generatedCode": generated_code, "success": True})
        if st == 201:
            n = (res or {}).get("patternsStored", 0)
            processed += 1
            learned_total += n
            print(f"  +{n:>2}  {d.name[:58]}  ({len(files)} file(s))")
            existing.add(f"{request} - Full architecture")
        else:
            print(f"  !! {d.name[:58]}: status={st} {str(res)[:120]}")
        time.sleep(0.25)

    after = store_titles()
    print(f"DONE — {processed} exports backfilled, +{learned_total} pattern(s) added "
          f"(store {len(existing)} → {len(after)}), {skipped} skipped "
          f"(broken/duplicate/no-ts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
