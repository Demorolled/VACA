#!/usr/bin/env python3
"""
Distill the 27B AEON's answers on a balanced sample of the VACA corpus.

Queries DSpark (127.0.0.1:8000, currently serving the 27B AEON Q4) with each
sampled row's instruction+input and saves the 27B's output as the new training
target. The 14B round then learns to answer like the 27B.

Usage:
  python3 scripts/distill-27b-vaca.py                 # balanced ~400 rows
  python3 scripts/distill-27b-vaca.py --rows 400 --seed 42
  python3 scripts/distill-27b-vaca.py --api http://127.0.0.1:8000
"""
import argparse
import json
import random
import time
import urllib.request
import urllib.error
from pathlib import Path

API = "http://127.0.0.1:8000/v1/chat/completions"
SRC = "/home/llmlab/Desktop/visual-ai-architect/training/cloud/round25/all.jsonl"
OUT = "/home/llmlab/Desktop/visual-ai-architect/training/cloud/round28-distill-27b.jsonl"
LOG = "/home/llmlab/Desktop/visual-ai-architect/training/cloud/round28-distill-27b.log"

# Per-category max_tokens: the 27B is verbose and hits a flat cap even on
# short-answer rows, wasting most of the wall-clock. Cap tight per category.
CATEGORY_MAX_TOKENS = {
    "code": 2000,
    "plan": 500,
    "reasoning": 500,
    "knowledge": 250,
    "identity": 250,
    "verify": 400,
    "?": 500,
}
CATEGORIES = list(CATEGORY_MAX_TOKENS.keys())


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ask_27b(instruction: str, user_input: str, api: str, max_tokens: int = 1500) -> str:
    """One OpenAI-compatible chat completion against the 27B."""
    content = instruction
    if user_input:
        content += "\n\n" + user_input
    body = json.dumps({
        "model": "x",  # dspark serves one model; ignored
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }).encode()
    req = urllib.request.Request(api, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        j = json.loads(r.read())
    return j["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--api", default=API)
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override the per-category cap with a flat cap (rows arg wins).")
    args = ap.parse_args()

    def max_tokens_for(cat):
        return args.max_tokens or CATEGORY_MAX_TOKENS.get(cat, 500)

    random.seed(args.seed)
    rows = [json.loads(l) for l in open(SRC) if l.strip()]
    log(f"source: {len(rows)} rows from {SRC}")

    # Resume: skip instructions already distilled (keyed on instruction+input).
    done_keys = set()
    if Path(OUT).exists():
        for line in open(OUT):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done_keys.add((r.get("instruction", ""), r.get("input", "")))
            except json.JSONDecodeError:
                pass
    if done_keys:
        log(f"resume: {len(done_keys)} rows already distilled — skipping them")

    # Balanced sample: keep the category proportions of the source.
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r.get("category", "?"), []).append(r)
    sample = []
    target = args.rows
    for cat in sorted(by_cat):
        pool = by_cat[cat]
        n = max(1, round(target * len(pool) / len(rows)))
        sample.extend(random.sample(pool, min(n, len(pool))))
    random.shuffle(sample)
    sample = sample[:target]
    log(f"sampled {len(sample)} rows (balanced): " +
        ", ".join(f"{c}={sum(1 for r in sample if r.get('category')==c)}"
                  for c in sorted(set(r.get('category','?') for r in sample))))

    # Filter the sample down to not-yet-done rows.
    sample = [r for r in sample
              if (r.get("instruction", ""), r.get("input", "")) not in done_keys]
    log(f"remaining to distill: {len(sample)}")

    done = 0
    fails = 0
    t0 = time.time()
    with open(OUT, "a") as f:
        for i, r in enumerate(sample):
            instruction = r.get("instruction", "")
            user_input = r.get("input", "")
            try:
                out = ask_27b(instruction, user_input, args.api, max_tokens_for(r.get("category", "?")))
                if not out:
                    raise ValueError("empty output")
                row = {
                    "instruction": instruction,
                    "input": user_input,
                    "output": out,
                    "source": "r28:distill-27b",
                    "category": r.get("category", "?"),
                    "orig_source": r.get("source", ""),
                }
                f.write(json.dumps(row) + "\n")
                f.flush()
                done += 1
            except Exception as e:  # noqa: BLE001
                fails += 1
                log(f"  FAIL row {i}: {str(e)[:120]}")
            if (i + 1) % 20 == 0:
                el = (time.time() - t0) / 60
                rate = (i + 1) / max(el, 0.001)
                eta = (len(sample) - i - 1) / max(rate, 0.001) / 60
                log(f"  {i+1}/{len(sample)} done={done} fails={fails} "
                    f"({rate:.1f} rows/min, ETA {eta:.0f} min)")

    log(f"DONE: {done} rows -> {OUT} ({fails} fails) in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
