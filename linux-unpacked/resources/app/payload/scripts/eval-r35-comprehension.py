#!/usr/bin/env python3
"""
eval-r35-comprehension.py — score R35 on HELD-OUT code-comprehension triples.
================================================================================
Runs the merged R35 checkpoint against the held-out val rows (families the
model never trained on). Each row is pick-from-3: output is the single
letter A/B/C. We score it two ways:

  exact  : model's first answer token must be the correct letter
  starts : model's answer must START with the correct letter (tolerates a
           trailing explanation like "A — clamp because...")

Also reports per-direction accuracy (purpose→code, code→purpose, gap→chunk)
so we can see WHICH understanding skill the round improved.

Usage (ON THE AGENT, venv python):
  /home/llmlab/vaca-train-venv/bin/python scripts/eval-r35-comprehension.py \
      /home/llmlab/Desktop/visual-ai-architect/training/cloud/out/round35/merged
"""
import json
import re
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

VAL = Path("/home/llmlab/vaca-r35/training/val.jsonl")
SYSTEM_PROMPT = (
    "You are a Visual AI Architect assistant specializing in GUI development. "
    "You build complete web applications, explain UI patterns, generate code, "
    "and help with frontend development."
)


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else None
    val_path = Path(sys.argv[2]) if len(sys.argv) > 2 else VAL
    if not ckpt:
        print("usage: eval-r35-comprehension.py <merged-checkpoint-dir> [val.jsonl]")
        sys.exit(1)
    ckpt = Path(ckpt)
    if not (ckpt / "config.json").exists():
        print(f"❌ no config.json at {ckpt}")
        sys.exit(1)

    print(f"⬇️  Loading {ckpt} fp16…")
    tok = AutoTokenizer.from_pretrained(str(ckpt), trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(ckpt), torch_dtype=torch.float16, device_map="auto",
        trust_remote_code=True, low_cpu_mem_usage=True,
    )
    model.eval()

    rows = []
    for line in val_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("category") == "gen":
            continue  # comprehension eval scores only the MC rows
        if not r.get("output") or r["output"] not in "ABC":
            continue
        rows.append(r)
    print(f"✅ val MC rows: {len(rows)}")

    exact = starts = 0
    per_dir = {}
    for i, r in enumerate(rows):
        user = f"{r['instruction']}\n\n{r['input']}".strip() if r.get("input") else r["instruction"]
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        ids = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_tensors="pt")
        if hasattr(ids, "input_ids"):  # transformers 5.x returns a BatchEncoding wrapper
            ids = ids.input_ids
        with torch.no_grad():
            out = model.generate(
                ids.to(model.device),
                max_new_tokens=24,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
        gen = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True).strip()
        ans = r["output"]
        m = re.match(r"^\s*([ABC])", gen)
        first = m.group(1) if m else None
        hit_exact = first == ans
        hit_starts = hit_exact
        exact += hit_exact
        starts += hit_starts
        cat = r.get("category", "mc-code")
        d = per_dir.setdefault(cat, {"n": 0, "ok": 0})
        d["n"] += 1
        d["ok"] += hit_exact
        if i < 4 or not hit_exact:
            print(f"  [{cat}] ans={ans} got={first or '(none)'} {'✅' if hit_exact else '❌'} :: {r['source']}")
        if (i + 1) % 100 == 0:
            print(f"  … {i+1}/{len(rows)}")

    n = len(rows)
    print(f"\n=== COMPREHENSION: exact {exact}/{n} ({100 * exact / n:.1f}%) | "
          f"starts {starts}/{n} ({100 * starts / n:.1f}%) ===")
    print("per-direction (exact):")
    for cat, d in sorted(per_dir.items()):
        print(f"  {cat:12s} {d['ok']}/{d['n']} ({100 * d['ok'] / d['n']:.1f}%)")


if __name__ == "__main__":
    main()