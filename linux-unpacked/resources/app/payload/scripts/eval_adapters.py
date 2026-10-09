#!/usr/bin/env python3
"""
eval_adapters.py — the FIRST gate: how close is the output to the gold file?
================================================================================
This is the older gate, kept for history and comparison. It scores a candidate
by difflib similarity against the gold file for the corpus's HELD-OUT tasks.

It is SATURATED and is no longer the deciding metric:
    base 0.3814   (the untouched base model)
    nogrpo / nogrpo2 / curated   0.6659 – 0.6861  with code_like 7/7
Every SFT arm lands in the same 0.66–0.69 band and every one is "code-like", so
the number cannot separate a file that COMPILES from one that merely resembles
the gold. That is exactly why scripts/eval_acceptance.py (parse + declared
exports) exists. Keep this around to reproduce the historical numbers and to see
that the two gates disagree.

Same task file, same prompt, same temp 0 / seed 42 generation as eval_acceptance,
so the two gates are comparing like with like.

Usage:
  python3 scripts/eval_adapters.py \
      --gold corpora/vaca/gold.jsonl --meta corpora/vaca/meta.json \
      --model base=vaca-r40-off-adapter:latest \
      --model distill=vaca-r40-off-distill-adapter:latest \
      --baseline base --out runs/adapters-distill.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import difflib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_GOLD = ROOT / "corpora" / "vaca" / "gold.jsonl"
DEFAULT_META = ROOT / "corpora" / "vaca" / "meta.json"
API = "http://192.168.1.234:11434/api/generate"
COMPLETION_PREFIX = "Recreate this file. Output the file content only.\n\n"

# A reply is "code-like" if it carries at least one structural code signal — the
# historical gate had this pinned at 7/7 for every arm, which is the tell that it
# stopped discriminating.
CODE_SIGNAL_RE = re.compile(r"(export |function |=>|\bconst \b|\bclass \b|[{};])")


def gen(api: str, model: str, prompt: str, num_predict: int, num_ctx: int) -> str:
    payload = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "seed": 42,
                    "num_predict": num_predict, "num_ctx": num_ctx},
        "keep_alive": "10m",
    }
    req = urllib.request.Request(api, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())["response"]


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(DEFAULT_GOLD))
    ap.add_argument("--meta", default=str(DEFAULT_META))
    ap.add_argument("--model", action="append", required=True, metavar="NAME=TAG")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--api", default=API)
    ap.add_argument("--num-predict", type=int, default=1200)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--held-out-only", action="store_true", default=True)
    ap.add_argument("--all", dest="held_out_only", action="store_false")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    gold_path = Path(args.gold).expanduser()
    meta = json.loads(Path(args.meta).expanduser().read_text()) if Path(args.meta).exists() else {}
    held = set(meta.get("held_out_ids") or [])
    rows = [json.loads(l) for l in gold_path.read_text().splitlines() if l.strip()]
    if args.held_out_only:
        rows = [r for r in rows if r["id"] in held] or rows
    if not rows:
        print("[eval] ABORT: no gold rows", file=sys.stderr)
        return 1

    models = []
    for m in args.model:
        if "=" not in m:
            print(f"[eval] ABORT: --model needs NAME=TAG, got {m!r}", file=sys.stderr)
            return 1
        models.append(tuple(m.split("=", 1)))
    names = [n for n, _ in models]

    print(f"[eval] gold={gold_path} tasks={len(rows)} held_out_only={args.held_out_only}")
    print(f"[eval] temp=0 seed=42 num_predict={args.num_predict} num_ctx={args.num_ctx}")

    summary = {}
    for name, tag in models:
        t0 = time.time()
        sims, code_like = [], 0
        for r in rows:
            prompt = COMPLETION_PREFIX + (
                f"id={r['id']} file={r['file']} lang={r['lang']}"
                + (f" | expected exports: {', '.join(r['expected_exports'])}" if r.get("expected_exports") else "")
                + (f" | task: {r.get('request') or ''}" if r.get("request") else "")
            )
            try:
                out = gen(args.api, tag, prompt, args.num_predict, args.num_ctx)
            except Exception as e:  # noqa: BLE001
                print(f"[eval] {name} {r['id']}: generate failed ({type(e).__name__}: {e})")
                out = ""
            sims.append(ratio(out, r["gold"]))
            if CODE_SIGNAL_RE.search(out or ""):
                code_like += 1
        summary[name] = {
            "tag": tag, "n": len(rows),
            "mean_similarity": round(sum(sims) / len(sims), 4) if sims else None,
            "code_like": code_like,
            "elapsed_s": round(time.time() - t0, 1),
        }
        print(f"[eval] {name}: mean_similarity={summary[name]['mean_similarity']} "
              f"code_like={code_like}/{len(rows)} ({summary[name]['elapsed_s']}s)")

    base = summary[args.baseline]["mean_similarity"] if args.baseline in summary else None
    print("\n[eval] ================ SUMMARY ================")
    for n in names:
        s = summary[n]
        d = "" if base is None else f"  delta_vs_{args.baseline}={s['mean_similarity'] - base:+.4f}"
        print(f"[eval] {n:<12} mean_similarity={s['mean_similarity']:.4f}  "
              f"code_like={s['code_like']}/{s['n']}{d}")

    if args.out:
        outp = Path(args.out).expanduser()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({
            "gold": str(gold_path), "held_out_only": args.held_out_only,
            "n_tasks": len(rows), "baseline": args.baseline,
            "num_predict": args.num_predict, "num_ctx": args.num_ctx,
            "summary": summary,
        }, indent=2) + "\n")
        print(f"[eval] wrote {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
