#!/usr/bin/env python3
"""
Build Ladder Harness
====================
Drives the 40-build ladder (data/build-ladder-40.md) through the REAL builder
app (/api/blueprint/build), monitors dspark token consumption, verifies each
build's pipeline verdict (tsCompileClean / errors / verified capture / drift),
runs a post-build runtime-smoke on HTML entries, and appends one JSON object
per build to data/build-ladder-results.jsonl.

Usage:
  python3 scripts/run-build-ladder.py [--ladder data/build-ladder-40.md]
                                      [--start N] [--end N]
                                      [--results data/build-ladder-results.jsonl]
                                      [--interval 30] [--timeout 1800]
                                      [--skip-smoke]
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
API = "http://localhost:3001"
DSPARK = "http://localhost:8000"
RESP_DIR = str(ROOT / "data" / "ladder-responses")

# ── API helpers ────────────────────────────────────────────────────────────

def post(url: str, body: dict, timeout: int = 60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def get(url: str, timeout: int = 15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)

def dspark_stats() -> dict:
    try:
        d = get(f"{DSPARK}/v1/health", timeout=8)
        return {
            "tokens": (d.get("stats") or {}).get("total_completion_tokens", 0),
            "requests": (d.get("stats") or {}).get("requests", 0),
        }
    except Exception:
        return {"tokens": None, "requests": None}

# ── Ladder parsing ─────────────────────────────────────────────────────────

def parse_ladder(path: Path):
    """Parse the ladder markdown table rows: goal | blueprint | score | nodes."""
    builds = []
    tier = None
    for line in path.read_text().splitlines():
        tm = re.match(r"^## Tier (\d+) ", line)
        if tm:
            tier = int(tm.group(1))
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|\s*~(\d+)", line)
        if not m:
            continue
        builds.append({
            "number": int(m.group(1)),
            "goal": m.group(2).strip(),
            "expectedBlueprint": m.group(3).strip(),
            "expectedScore": float(m.group(4)),
            "expectedNodes": int(m.group(5)),
            "tier": tier,
        })
    return builds

# ── Runtime smoke (post-build verification) ────────────────────────────────

def run_smoke(files):
    """POST /api/generate/runtime-smoke with the generated files; returns verdict."""
    if not files:
        return {"status": "skipped", "detail": "no files"}
    html = next((f for f in files if (f.get("fileName") or f.get("path") or "").endswith(".html")), None)
    if not html:
        return {"status": "skipped", "detail": "no HTML entry"}
    try:
        # Send ALL files: the smoke runner virtualizes the set so the HTML can
        # import its scripts.
        body = {"files": [{"fileName": f.get("fileName") or f.get("path"), "code": f.get("code") or f.get("content") or ""} for f in files]}
        d = post(f"{API}/api/generate/runtime-smoke", body, timeout=180)
        smoke = d.get("smoke") or {}
        return {
            "status": "pass" if smoke.get("success") else "fail",
            "available": smoke.get("available"),
            "checks": [c.get("name") for c in smoke.get("checks", [])],
            "passCount": sum(1 for c in smoke.get("checks", []) if c.get("status") == "pass"),
            "totalChecks": len(smoke.get("checks", [])),
            "consoleErrors": len(smoke.get("consoleErrors", []) or []),
            "durationMs": smoke.get("durationMs"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# ── One build ──────────────────────────────────────────────────────────────

def run_build(b: dict, interval: int, timeout: int, skip_smoke: bool):
    goal = b["goal"]
    print(f"\n{'='*70}\n[{b['number']:02d}] BUILD: {goal}")
    print(f"  expected: {b['expectedBlueprint']} (score {b['expectedScore']}, ~{b['expectedNodes']} nodes)")

    start = time.time()
    before = dspark_stats()

    # Launch the build (long-running; the route generates + validates).
    try:
        resp = post(f"{API}/api/blueprint/build",
                    {"goal": goal, "targetOS": "linux", "scale": "medium"},
                    timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        return {"goal": goal, "number": b["number"], "error": f"HTTP {e.code}: {detail}",
                "durationMs": int((time.time() - start) * 1000)}
    except Exception as e:
        return {"goal": goal, "number": b["number"], "error": str(e),
                "durationMs": int((time.time() - start) * 1000)}

    after = dspark_stats()
    elapsed = time.time() - start

    # Dump the raw response for deep-dive analysis — the ONLY place the
    # generated code survives (projects.json keeps nodes 'pending').
    try:
        resp_dir = Path(RESP_DIR)
        resp_dir.mkdir(parents=True, exist_ok=True)
        (resp_dir / f"{b['number']:02d}.json").write_text(json.dumps(resp, indent=1))
    except Exception:
        pass

    # Response is FLAT: files / tsCompileClean / totalErrors / verifiedCapture /
    # drift all sit at the top level, with a summary sub-object mirroring them.
    files = resp.get("files") or []
    summary = resp.get("summary") or {}
    capture = resp.get("verifiedCapture") or {}
    drift = resp.get("drift") or {}
    internal = resp.get("internalKnowledge") or {}
    research = resp.get("research") or {}
    timing = resp.get("timingMs") or {}

    # Compact per-file errors (first 3 per file, capped) for the report.
    fileErrors = {}
    for f in files:
        raw = f.get("errors") or []
        errs = [(e.get("message") if isinstance(e, dict) else str(e)) for e in raw][:3]
        if errs:
            fileErrors[f.get("fileName") or f.get("path")] = errs

    # Post-build runtime smoke on the HTML entry (if any).
    smoke = None if skip_smoke else run_smoke(files)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "number": b["number"],
        "goal": goal,
        "expectedBlueprint": b["expectedBlueprint"],
        "expectedScore": b["expectedScore"],
        "expectedNodes": b["expectedNodes"],
        "matchedBlueprint": (resp.get("blueprint") or {}).get("app_type"),
        "matchScore": resp.get("matchScore"),
        "matchedBy": resp.get("matchedBy"),
        "tier": b.get("tier"),
        "projectId": resp.get("projectId"),
        "researchInjected": bool(research.get("searched")),
        "internalKnowledgeInjected": bool(internal.get("searched")),
        "durationMs": timing.get("total", int(elapsed * 1000)),
        "totalChars": summary.get("totalChars") or resp.get("totalChars"),
        "totalFiles": summary.get("totalFiles") or len(files),
        "tsCompileClean": resp.get("tsCompileClean") if resp.get("tsCompileClean") is not None else summary.get("tsCompileClean"),
        "totalErrors": summary.get("totalErrors") if summary.get("totalErrors") is not None else resp.get("totalErrors"),
        "validatedCount": summary.get("validated") if summary.get("validated") is not None else resp.get("validatedCount"),
        "failedCount": summary.get("failed") if summary.get("failed") is not None else resp.get("failedCount"),
        "isAllValidated": summary.get("isAllValidated") if summary.get("isAllValidated") is not None else (resp.get("validatedCount") == len(files) if len(files) else resp.get("success")),
        "errorCount": resp.get("error") or (len([f for f in files if f.get("errors")]) if files else 0),
        "fileErrors": fileErrors or None,
        "verifiedCapture": {
            "captured": capture.get("captured"),
            "skipped": capture.get("skipped"),
            "reasons": capture.get("reasons"),
        },
        "drift": {
            "clean": drift.get("clean") if isinstance(drift, dict) else None,
            "matched": drift.get("matched") if isinstance(drift, dict) else None,
            "missing": drift.get("missing") if isinstance(drift, dict) else None,
            "unexpected": drift.get("unexpected") if isinstance(drift, dict) else None,
        },
        "dsparkTokensDelta": (after["tokens"] - before["tokens"]) if before["tokens"] is not None and after["tokens"] is not None else None,
        "dsparkRequestsDelta": (after["requests"] - before["requests"]) if before["requests"] is not None and after["requests"] is not None else None,
        "runtimeSmoke": smoke,
        "success": resp.get("success"),
        "error": resp.get("error"),
    }

    # Compact console verdict.
    verdict = "PASS" if (record["isAllValidated"] and record["tsCompileClean"]) else "FAIL"
    print(f"  → matched: {record['matchedBlueprint']} ({record['matchScore']}) [{record['matchedBy']}]")
    print(f"  → verdict: {verdict} | tscClean={record['tsCompileClean']} errors={record['totalErrors']} "
          f"validated={record['validatedCount']}/{record['totalFiles']}")
    print(f"  → research={record['researchInjected']} internalKnowledge={record['internalKnowledgeInjected']} "
          f"captured={record['verifiedCapture'].get('captured')}")
    if smoke:
        print(f"  → runtime-smoke: {smoke.get('status')} ({smoke.get('passCount')}/{smoke.get('totalChecks')} checks, "
              f"{smoke.get('consoleErrors')} console errors)")
    print(f"  → duration: {record['durationMs']/1000:.1f}s | dspark tokens: {record['dsparkTokensDelta']}")

    return record

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Build ladder harness")
    ap.add_argument("--ladder", default=str(ROOT / "data" / "build-ladder-40.md"))
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=999)
    ap.add_argument("--results", default=str(ROOT / "data" / "build-ladder-results.jsonl"))
    ap.add_argument("--interval", type=int, default=30, help="(kept for compat) poll interval")
    ap.add_argument("--timeout", type=int, default=1800, help="per-build HTTP timeout seconds")
    ap.add_argument("--skip-smoke", action="store_true")
    args = ap.parse_args()

    ladder = parse_ladder(Path(args.ladder))
    selected = [b for b in ladder if args.start <= b["number"] <= args.end]
    if not selected:
        print("No builds in range", args.start, "-", args.end)
        sys.exit(1)

    print(f"Ladder: {len(selected)} builds ({selected[0]['number']}–{selected[-1]['number']})")

    results_path = Path(args.results)
    results_path.parent.mkdir(parents=True, exist_ok=True)

    for b in selected:
        record = run_build(b, args.interval, args.timeout, args.skip_smoke)
        with open(results_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"  [logged] {results_path}")

    # Summary table
    print("\n" + "=" * 70)
    print("LADDER SUMMARY")
    print("=" * 70)
    rows = [json.loads(l) for l in results_path.read_text().splitlines() if l.strip()]
    passes = sum(1 for r in rows if r.get("isAllValidated"))
    print(f"completed: {len(rows)} | allValidated: {passes} | failed: {len(rows) - passes}")
    for r in rows:
        status = "PASS" if r.get("isAllValidated") else "FAIL"
        print(f"  [{r.get('number'):02d}] {r.get('goal','')[:45]:47s} → {str(r.get('matchedBlueprint'))[:28]:30s} "
              f"{status} err={r.get('totalErrors')} cap={r.get('verifiedCapture',{}).get('captured')}")

if __name__ == "__main__":
    main()
