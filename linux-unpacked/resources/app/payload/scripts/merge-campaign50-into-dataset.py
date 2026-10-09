#!/usr/bin/env python3
"""
Merge campaign50-corrected.jsonl into the training dataset and re-split
=======================================================================
The corrected campaign-50 examples (215 per-node source files) teach the
import/export/no-JSX contract, self-contained-corrected examples (named-only,
zero-import, no-delegation rewrites) counter the tuned model's delegation habit,
and captured-verified examples
(tsc-clean exports whose rows carry the retrieved library context in `input`)
teach it to generate code conditioned on the reference library. Merging them
INTO the main dataset (rather than training on them alone) lets the model ALSO
keep its general GUI knowledge from the existing 2,847 train examples.

Key design decision:
  The campaign + captured examples are the PRIMARY teaching signals (fixed
  contract + library-conditioned generation), so ALL of them are guaranteed
  into the train split. The existing pool (train + val + test) is shuffled and
  used to fill train up to 80%, with the remainder split 50/50 into val/test
  (matching the original 80/10/10 ratio).

Approach:
  - Pool = existing train.jsonl + val.jsonl + test.jsonl
           + campaign50-corrected.jsonl + captured-verified.jsonl
  - Dedupe on (instruction, input, output), priority sources win on collision
  - priority (campaign50 + captured) examples → train (all of them)
  - train filled to 80% from the shuffled existing pool; rest → val/test
  - Back up the original 4 files to training/dataset/backup-<timestamp>/
  - Overwrite train.jsonl / val.jsonl / test.jsonl
  - Update dataset_meta.json totals + sources

Usage:
  python3 scripts/merge-campaign50-into-dataset.py
"""

import json, os, random, shutil, sys, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(BASE, "training", "dataset")

CAMPAIGN = os.path.join(DS, "campaign50-corrected.jsonl")
CAPTURED = os.path.join(DS, "captured-verified.jsonl")
VERIFIED = os.path.join(DS, "verified-generations.jsonl")
SELF_CONTAINED = os.path.join(DS, "self-contained-corrected.jsonl")
VACA = os.path.join(DS, "vaca-knowledge.jsonl")
FILES = {
    "train": os.path.join(DS, "train.jsonl"),
    "val": os.path.join(DS, "val.jsonl"),
    "test": os.path.join(DS, "test.jsonl"),
}
META = os.path.join(DS, "dataset_meta.json")

SEED = 42
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1


def read_jsonl(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ⚠️  Skipping malformed line in {path}: {e}")
    return recs


def write_jsonl(path, recs):
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def key(r):
    return (r.get("instruction", ""), r.get("input", ""), r.get("output", ""))


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("⚠️  DRY RUN — printing the split plan without writing any files.\n")

    if not os.path.isfile(CAMPAIGN):
        print(f"❌ {CAMPAIGN} not found — run export-corrected-builds-to-training.py first.")
        sys.exit(1)

    # ── Load pool ─────────────────────────────────────────────────────
    existing = []
    for name, path in FILES.items():
        if os.path.isfile(path):
            recs = read_jsonl(path)
            existing.extend(recs)
            print(f"  Loaded {name}: {len(recs)} examples")
        else:
            print(f"  ⚠️  Missing {name} ({path}) — continuing without it")

    campaign = read_jsonl(CAMPAIGN)
    print(f"  Loaded campaign50-corrected: {len(campaign)} examples")

    captured = read_jsonl(CAPTURED) if os.path.isfile(CAPTURED) else []
    if captured:
        print(f"  Loaded captured-verified: {len(captured)} examples")
    else:
        print("  captured-verified.jsonl: empty or missing — continuing without it")

    verified = read_jsonl(VERIFIED) if os.path.isfile(VERIFIED) else []
    if verified:
        print(f"  Loaded verified-generations (canvas auto-capture): {len(verified)} examples")
    else:
        print("  verified-generations.jsonl: empty or missing — continuing without it")

    if not os.path.isfile(SELF_CONTAINED):
        print(f"❌ {SELF_CONTAINED} not found — run build-self-contained-corrected.py first.")
        sys.exit(1)
    self_contained = read_jsonl(SELF_CONTAINED)
    print(f"  Loaded self-contained-corrected: {len(self_contained)} examples")

    vaca = read_jsonl(VACA) if os.path.isfile(VACA) else []
    if vaca:
        print(f"  Loaded vaca-knowledge: {len(vaca)} examples")
    else:
        print("  vaca-knowledge.jsonl: empty or missing — continuing without it")

    total_before = len(existing) + len(campaign) + len(captured) + len(verified) + len(self_contained) + len(vaca)

    # ── Dedupe (prefer priority sources on exact collision) ────────────
    # Priority order: campaign50 → self-contained → captured → verified →
    # vaca-knowledge → existing (priority sources win over existing duplicates).
    seen = set()
    pool = []
    for r in campaign + self_contained + captured + verified + vaca + existing:
        k = key(r)
        if k in seen:
            continue
        seen.add(k)
        pool.append(r)
    print(f"  Pool after dedupe: {len(pool)} (removed {total_before - len(pool)} duplicates)")

    # ── Split: priority (campaign + captured + verified + vaca) → train; fill from pool ──
    priority_keys = {key(r) for r in campaign + self_contained + captured + verified + vaca}
    priority_recs = [r for r in pool if key(r) in priority_keys]
    existing_pool = [r for r in pool if key(r) not in priority_keys]

    # Sort by a stable key BEFORE the seeded shuffle. Without this, re-running
    # the merge is NOT deterministic: the "existing" pool is re-read from the
    # previous run's (already shuffled) train/val/test files, so the seeded
    # shuffle applies its position permutation to a different input order each
    # run → records silently migrate between splits → fine-tune runs are not
    # comparable. Sorting first makes the pre-shuffle order canonical.
    existing_pool.sort(key=key)

    rng = random.Random(SEED)
    rng.shuffle(existing_pool)

    n_train = int(len(pool) * TRAIN_RATIO)
    n_val = int(len(pool) * VAL_RATIO)

    if len(priority_recs) > n_train:
        print("❌ Priority (campaign+self-contained+captured) examples exceed the train budget — aborting (no writes).")
        sys.exit(1)

    fill_needed = n_train - len(priority_recs)
    train = priority_recs + existing_pool[:fill_needed]
    rest = existing_pool[fill_needed:]
    # val:test ratio 1:1 (matches 80/10/10 with equal halves)
    n_val_rest = min(len(rest) // 2, n_val)
    val = rest[:n_val_rest]
    test = rest[n_val_rest:]

    print(f"  Priority examples in train: {len(priority_recs)} (campaign {len(campaign)}, self-contained {len(self_contained)}, captured {len(captured)}, verified {len(verified)}, vaca {len(vaca)})")

    if dry_run:
        print(f"\n  Would write (dry run — nothing written):")
        print(f"   train.jsonl: {len(train)}")
        print(f"   val.jsonl:   {len(val)}")
        print(f"   test.jsonl:  {len(test)}")
        print(f"   total:       {len(pool)}")
        return

    # ── Backup originals ──────────────────────────────────────────────
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(DS, f"backup-{ts}")
    os.makedirs(backup_dir, exist_ok=True)
    for name, path in FILES.items():
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    # META is also overwritten below — back it up too so a validation run is
    # fully revertible (train/val/test alone are not enough to restore state).
    if os.path.isfile(META):
        shutil.copy2(META, os.path.join(backup_dir, os.path.basename(META)))
    print(f"  💾 Backed up originals → {backup_dir}")

    # ── Write new splits ──────────────────────────────────────────────
    write_jsonl(FILES["train"], train)
    write_jsonl(FILES["val"], val)
    write_jsonl(FILES["test"], test)
    print(f"\n✅ Wrote:")
    print(f"   train.jsonl: {len(train)} (incl. {len(priority_recs)} priority: campaign {len(campaign)} + self-contained {len(self_contained)} + captured {len(captured)} + verified {len(verified)} + vaca {len(vaca)})")
    print(f"   val.jsonl:   {len(val)}")
    print(f"   test.jsonl:  {len(test)}")
    print(f"   total:       {len(pool)}")

    # ── Update dataset_meta.json ──────────────────────────────────────
    if os.path.isfile(META):
        with open(META, encoding="utf-8") as f:
            meta = json.load(f)
        meta["total_examples"] = len(pool)
        meta["train_examples"] = len(train)
        meta["val_examples"] = len(val)
        meta["test_examples"] = len(test)
        meta["merged_priority_sources"] = {
            "campaign_examples_added": len(campaign),
            "self_contained_examples_added": len(self_contained),
            "captured_examples_added": len(captured),
            "verified_generations_added": len(verified),
            "vaca_knowledge_added": len(vaca),
            "priority_in_train": len(priority_recs),
            "merged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seed": SEED,
        }
        meta.pop("merged_campaign50", None)  # renamed key — drop stale entry from older runs
        sources = meta.get("sources", [])
        for src in ("campaign50-corrected.jsonl", "self-contained-corrected.jsonl", "captured-verified.jsonl", "verified-generations.jsonl", "vaca-knowledge.jsonl"):
            if src not in sources:
                sources.append(src)
        meta["sources"] = sources
        with open(META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"   Updated {os.path.basename(META)}")


if __name__ == "__main__":
    main()
