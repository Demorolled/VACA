#!/usr/bin/env python3
"""
build-sky1-sft-corpus.py — Convert Sky-T1_data_17k → VACA SFT corpus (JSONL).

Sky-T1 rows are {system, conversations:[{role, content, weight}...]} — single
reasoning question/answer traces (the "$450 o1-preview recipe"). VACA's
train_round1.py SFT path reads flat {instruction, input, output} JSONL with
assistant-only label masking. So:

  - each Sky-T1 row → one (user turn → assistant turn) SFT example:
        instruction = the user question (with thinking prefix stripped)
        output      = the assistant's full answer, INCLUDING its backtick
                      thinking trace (that's the whole point — teach the model
                      to reason before it answers)
        input       = "" (Sky-T1 is single-turn)

Options:
  --src PATH           Sky-T1 json (default: auto-find on the 4TB drive / local)
  --out-dir PATH       output dir (default: training/cloud/sky1)
  --max-rows N         cap examples (default 6000 for a fast first Kaggle run)
  --seq-cap N          max tokens-ish guard: skip rows whose answer is enormous
  --keep-thinking      (default) keep the assistant's thinking trace in output
  --strip-thinking     drop the  ̂̂̂ / ```thinking``` block, answer only
  --dry-run            print stats and a sample, write nothing
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_source(src: str | None) -> Path:
    if src:
        p = Path(src)
        if p.exists():
            return p
        print(f"❌ --src not found: {src}")
        sys.exit(1)
    candidates = [
        ROOT / "training" / "dataset" / "sky-t1" / "Sky-T1_data_17k.json",
        Path("/media/final-flash1/896cb451-b4ef-4800-9f48-6e9a28a0fd73/Datasets/sky-t1/Sky-T1_data_17k.json"),
    ]
    for c in candidates:
        if c.exists():
            return c
    print("❌ Could not auto-locate Sky-T1_data_17k.json — pass --src")
    sys.exit(1)


def user_turns(conversations) -> list:
    """Return list of (user_text, assistant_text) pairs for a Sky-T1 row.

    Sky-T1 rows use {'from': 'user'|'assistant', 'value': str} messages
    (not 'role'/'content'). Each row is a single reasoning Q→A.
    """
    pairs = []
    pending_user = None
    for msg in conversations:
        role = msg.get("from", msg.get("role", ""))
        content = msg.get("value", msg.get("content", "")) or ""
        role = (role or "").lower()
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            pairs.append((pending_user, content))
            pending_user = None
    return pairs


def strip_thinking(answer: str) -> str:
    """Remove the <|begin_of_thought|>...<|end_of_thought|> reasoning trace.

    Returns just the final answer. Used with --strip-thinking.
    """
    lo = answer.find("<|begin_of_thought|>")
    hi = answer.find("<|end_of_thought|>")
    if lo != -1 and hi != -1:
        tail = answer[hi + len("<|end_of_thought|>"):]
        return tail.strip()
    return answer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "training" / "cloud" / "sky1"))
    ap.add_argument("--max-rows", type=int, default=6000)
    ap.add_argument("--seq-cap", type=int, default=4096,
                    help="skip rows whose combined user+answer exceeds ~this many chars")
    ap.add_argument("--keep-thinking", action="store_true", default=True)
    ap.add_argument("--strip-thinking", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = find_source(args.src)
    print(f"📖 Reading {src} ...")
    data = json.load(open(src, "r", encoding="utf-8"))
    print(f"   {len(data)} Sky-T1 rows")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    examples = []
    skipped_short = 0
    skipped_long = 0
    for row in data:
        for user, answer in user_turns(row.get("conversations", [])):
            if len(answer.strip()) < 10:
                skipped_short += 1
                continue
            if len(user) + len(answer) > args.seq_cap:
                skipped_long += 1
                continue
            output = strip_thinking(answer) if args.strip_thinking else answer
            examples.append({
                "instruction": user.strip(),
                "input": "",
                "output": output.strip(),
            })
            if len(examples) >= args.max_rows:
                break
        if len(examples) >= args.max_rows:
            break

    random.seed(args.seed)
    random.shuffle(examples)

    total_tokens_cap = sum(len(e["instruction"]) + len(e["output"]) for e in examples)
    print(f"✅ {len(examples)} examples  (skipped short={skipped_short}, long={skipped_long})")
    print(f"   ~{total_tokens_cap/3.6/1e6:.1f}M tokens @ 3.6 ch/tok")

    sample = examples[0]
    print("\n── sample ──")
    print("instruction:", sample["instruction"][:120].replace("\n", " "))
    print("output (first 160):", sample["output"][:160].replace("\n", " "))

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    # train/val split 90/10 (train_round1.py also splits internally, so we keep val
    # but the dataset the pipeline pushes can just carry train).
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"
    n_val = max(1, int(len(examples) * 0.05))
    train, val = examples[: len(examples) - n_val], examples[len(examples) - n_val:]

    with open(train_path, "w", encoding="utf-8") as f:
        for e in train:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(val_path, "w", encoding="utf-8") as f:
        for e in val:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"📝 wrote {len(train)} → {train_path}  ({train_path.stat().st_size/1e6:.1f} MB)")
    print(f"📝 wrote {len(val)} → {val_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())