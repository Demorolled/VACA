#!/usr/bin/env python3
"""
promote-adapter.py — promote a VACA adapter on the ACCEPTANCE gate, not gold-sim.
================================================================================
The 7-task gold-similarity gate is saturated: every SFT arm lands in the same
0.66–0.69 band with code_like pinned 7/7, so it cannot rank adapters (measured
Δ ≈ +0.026 between the nogrpo and distill arms). The acceptance gate
(scripts/eval_acceptance.py --role completion: parse + declared exports) separates
the same arms by Δ ≈ +0.178 (nogrpo 0.5787 vs distill 0.7563 — corrected figures,
see runs/GATE_NUMBERS.md; the checker under-counted by ~20 points until its
wildcard shim was removed). This script makes the acceptance gate the DECISION:

  1. read the incumbent reasoning adapter from backend/llm-config.json
  2. score the incumbent + every candidate with eval_acceptance.py --role completion
  3. promote the best candidate ONLY if it beats the incumbent by --margin
  4. (--apply) back up llm-config.json and rewrite roles.reasoning.model, appending
     the gate evidence to the config _note

Default is a DRY RUN — it prints the table and the decision but writes nothing.
The orchestrator's PROMOTE stage passes --apply, so a training round ends by
selecting its adapter on this gate.

Usage:
  python3 scripts/promote-adapter.py                        # dry-run, auto candidates
  python3 scripts/promote-adapter.py --candidate vaca-r41-adapter:latest
  python3 scripts/promote-adapter.py --apply --margin 0.02  # the round's promotion step
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = ROOT / "backend" / "llm-config.json"
GATE = HERE / "eval_acceptance.py"
RUNS = ROOT / "runs"


def name_for(tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", tag)


def read_incumbent(config_path: Path) -> tuple[str, dict]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    model = ((cfg.get("roles") or {}).get("reasoning") or {}).get("model")
    if not model:
        raise SystemExit(f"[promote] ABORT: no roles.reasoning.model in {config_path}")
    return model, cfg


def discover_candidates(tags_url: str, incumbent: str) -> list[str]:
    with urllib.request.urlopen(tags_url, timeout=20) as r:
        tags = [m["name"] for m in json.loads(r.read()).get("models", [])]
    return [t for t in sorted(tags) if "adapter" in t and t != incumbent]


def run_gate(api: str, role: str, incumbent: str, candidates: list[str],
             max_tasks: int, out: Path) -> dict:
    cmd = [sys.executable, str(GATE), "--role", role,
           "--model", f"incumbent={incumbent}",
           "--baseline", "incumbent", "--api", api, "--out", str(out)]
    for t in candidates:
        cmd += ["--model", f"{name_for(t)}={t}"]
    if max_tasks:
        cmd += ["--max-tasks", str(max_tasks)]
    print(f"[promote] $ {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=ROOT)
    if rc.returncode != 0:
        raise SystemExit(f"[promote] ABORT: gate exited {rc.returncode}")
    return json.loads(out.read_text())


def rewrite_config(config_path: Path, tag: str, evidence: str) -> Path:
    backup = config_path.with_name(
        f"{config_path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}-promote")
    backup.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg.setdefault("roles", {}).setdefault("reasoning", {})["model"] = tag
    prev = cfg.get("_note", "")
    cfg["_note"] = (prev + " " if prev else "") + f"Promoted {time.strftime('%Y-%m-%d')}: {evidence}"
    config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return backup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--api", default="http://192.168.1.234:11434/api/generate")
    ap.add_argument("--role", choices=["completion", "app"], default="completion",
                    help="completion = file parses + exports (default); app = the file also "
                         "compiles against its real sibling files")
    ap.add_argument("--incumbent", default=None, help="override the config's current model")
    ap.add_argument("--candidate", action="append", default=None, metavar="TAG",
                    help="candidate tag (repeatable). Omit to auto-discover on the box.")
    ap.add_argument("--margin", type=float, default=0.0,
                    help="a candidate must beat the incumbent by more than this.")
    ap.add_argument("--max-tasks", type=int, default=0, help="cap tasks (0 = whole corpus)")
    ap.add_argument("--apply", action="store_true", help="write the winner to llm-config.json")
    args = ap.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    incumbent = args.incumbent or read_incumbent(config_path)[0]
    tags_url = args.api.rsplit("/api/", 1)[0] + "/api/tags"

    candidates = list(args.candidate) if args.candidate else discover_candidates(tags_url, incumbent)
    candidates = [c for c in candidates if c != incumbent]
    if not candidates:
        print(f"[promote] no candidates to evaluate (incumbent={incumbent}) — nothing to do")
        return 0
    print(f"[promote] role={args.role} incumbent={incumbent} candidates={candidates} "
          f"margin={args.margin} apply={args.apply}")

    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = RUNS / f"promotion-{args.role}-{stamp}.json"
    data = run_gate(args.api, args.role, incumbent, candidates, args.max_tasks, out)
    summary = data["summary"]

    inc_rate = summary["incumbent"]["pass_rate"]
    ranked = sorted((t for t in candidates if name_for(t) in summary),
                    key=lambda t: summary[name_for(t)]["pass_rate"], reverse=True)
    print(f"\n[promote] incumbent {incumbent}  pass_rate={inc_rate:.4f}")
    for t in ranked:
        s = summary[name_for(t)]
        print(f"[promote]   {t:<42} pass_rate={s['pass_rate']:.4f} "
              f"({s['passed']}/{s['n_applicable']})  delta={s['pass_rate'] - inc_rate:+.4f}")

    best = ranked[0] if ranked else None
    best_rate = summary[name_for(best)]["pass_rate"] if best else -1.0
    n_app = summary["incumbent"]["n_applicable"]
    promote = best is not None and best_rate > inc_rate + args.margin

    if not promote:
        print(f"[promote] KEEP incumbent (best {best} {best_rate:.4f} did not beat "
              f"{inc_rate:.4f} + {args.margin})")
        return 0

    evidence = (f"acceptance gate (--role {args.role}, n={n_app}): {best} pass_rate="
                f"{best_rate:.4f} vs incumbent {incumbent} {inc_rate:.4f} "
                f"(+{best_rate - inc_rate:.4f}). Chosen over gold-sim, which is saturated.")
    if not args.apply:
        print(f"[promote] WOULD PROMOTE {best} (evidence: {evidence}) — rerun with --apply")
        return 0

    backup = rewrite_config(config_path, best, evidence)
    print(f"[promote] PROMOTED {best} → {config_path} (backup {backup.name})")
    print(f"[promote] restart the backend to serve it; evidence in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
